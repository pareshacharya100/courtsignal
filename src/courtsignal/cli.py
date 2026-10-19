import argparse
import json
from pathlib import Path
import sys
from .config import Settings
from .models import Page
from .pipeline import ingest, load_manifest
from .providers import Claude, Voyage, Pinecone
from .search import search
from .sources import RecapSource
from .storage import Store
from .transport import browser_download


def emit(value):
    print(json.dumps(value, indent=2, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description='CourtSignal court-data pipeline')
    commands = parser.add_subparsers(dest='command', required=True)
    p = commands.add_parser('ingest', help='Download, validate and transactionally store a document manifest')
    p.add_argument('--manifest', default='examples/demo.json')
    p.add_argument('--refresh', action='store_true')
    p.add_argument('--report', type=Path)
    p = commands.add_parser('browser-fetch', help='Open challenge-protected public sources in your desktop browser, verify and ingest the download')
    p.add_argument('--manifest', default='examples/demo.json')
    p.add_argument('--downloads', type=Path, default=Path.home() / 'Downloads')
    p.add_argument('--timeout', type=int, default=180, help='Seconds to wait per document')
    p = commands.add_parser('recap', help='Read existing RECAP archive documents; no PACER purchases')
    p.add_argument('--docket-id', type=int, required=True)
    p.add_argument('--limit', type=int, default=5)
    p.add_argument('--max-pages', type=int, default=3, help='Maximum API pagination pages')
    p.add_argument('--output', type=Path, default=Path('data/recap-manifest.json'))
    p = commands.add_parser('search')
    p.add_argument('query')
    p.add_argument('--mode', choices=['keyword', 'semantic'], default='keyword')
    p.add_argument('--source', choices=['pacer', 'nyscef'])
    p.add_argument('--limit', type=int, default=5)
    p = commands.add_parser('enrich', help='Explicitly invoke the paid Claude API')
    p.add_argument('--document-id', required=True)
    p.add_argument('--max-pages', type=int, default=3)
    commands.add_parser('index', help='Explicitly embed current chunks with Voyage and upsert to Pinecone')
    p = commands.add_parser('answer', help='Explicitly invoke Claude over retrieved evidence')
    p.add_argument('question')
    p.add_argument('--mode', choices=['keyword', 'semantic'], default='keyword')
    p = commands.add_parser('evaluate')
    p.add_argument('--queries', type=Path, default=Path('examples/evaluation.json'))
    p.add_argument('--mode', choices=['keyword', 'semantic'], default='keyword')
    p.add_argument('--report', type=Path)
    p = commands.add_parser('serve')
    p.add_argument('--port', type=int, default=8000)
    commands.add_parser('status')
    p = commands.add_parser('export-demo', help='Export actual ingested data to a standalone offline explorer')
    p.add_argument('--output', type=Path, default=Path('docs/demo.html'))
    args = parser.parse_args()
    settings = Settings.from_env()
    store = Store(settings.database_url)
    try:
        if args.command == 'ingest':
            result = ingest(load_manifest(args.manifest), store, settings.data_dir, args.refresh)
            if args.report:
                args.report.parent.mkdir(parents=True, exist_ok=True)
                args.report.write_text(json.dumps(result, indent=2))
            emit(result)
            if any(d['status'] == 'quarantined' for d in result['documents']):
                return 1
        elif args.command == 'browser-fetch':
            # Only pinned documents not yet stored; the hash is what makes a browser download trustworthy.
            targets = [s for s in load_manifest(args.manifest) if s.expected_sha256 and not store.document(s.id)]
            documents = []
            for spec in targets:
                path, data = browser_download(spec.download_url, spec.expected_sha256, args.downloads, args.timeout)
                store.event(spec.id, 'browser_download', json.dumps({'url': spec.download_url, 'file': path.name}))
                documents += ingest([spec], store, settings.data_dir, downloader=lambda _, data=data: data)['documents']
            emit({'documents': documents, 'counts': store.counts()})
            if any(d['status'] == 'quarantined' for d in documents):
                return 1
        elif args.command == 'recap':
            specs = RecapSource(settings.courtlistener_token).documents(args.docket_id, args.limit, args.max_pages)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps([s.model_dump(mode='json') for s in specs], indent=2))
            emit({'manifest': str(args.output), 'available_documents': len(specs)})
        elif args.command == 'search':
            emit(search(store, settings, args.query, args.mode, args.limit, args.source))
        elif args.command == 'index':
            chunks = store.chunks()
            if not chunks:
                raise ValueError('Ingest documents before indexing')
            pinecone = Pinecone(settings)
            vectors = Voyage(settings).embed([h['text'] for h in chunks], 'document')
            emit({'upserted': pinecone.index(chunks, vectors), 'model': settings.voyage_model,
                  'dimension': settings.embedding_dimension, 'namespace': settings.pinecone_namespace})
        elif args.command == 'enrich':
            if not 1 <= args.max_pages <= 10:
                raise ValueError('max-pages must be between 1 and 10')
            doc = store.document(args.document_id)
            if not doc:
                raise ValueError('Unknown document ID; use the ingestion report')
            pages = [Page(**p) for p in store.query('SELECT number, text FROM pages WHERE document_id=? AND number<=? ORDER BY number', (args.document_id, args.max_pages))]
            result = Claude(settings).extract(pages)
            store.save_extraction(args.document_id, doc['content_hash'], settings.anthropic_model,
                {'pages_supplied': [p.number for p in pages], 'total_pages': doc['page_count'],
                 'partial_document': len(pages) < doc['page_count'], 'quote_presence_checked': True,
                 'entailment_verified': False}, result)
            emit(result.model_dump())
        elif args.command == 'answer':
            hits = search(store, settings, args.question, args.mode)
            result = Claude(settings).answer(args.question, hits)
            used = {c.chunk_id for c in result.claims}
            emit({'answer': result.model_dump(), 'sources': [h for h in hits if h['id'] in used],
                  'validation': 'Quote presence checked. Claim entailment requires human review.'})
        elif args.command == 'evaluate':
            rows = []
            for item in json.loads(args.queries.read_text()):
                hits = search(store, settings, item['query'], args.mode, limit=5)
                ranks = [i + 1 for i, h in enumerate(hits) if h['document_id'] == item['expected_document_id']]
                rows.append({**item, 'rank': min(ranks) if ranks else None})
            result = {'mode': args.mode, 'queries': len(rows), 'recall_at_5': sum(r['rank'] is not None for r in rows) / len(rows),
                      'mrr_at_5': sum(1 / r['rank'] if r['rank'] else 0 for r in rows) / len(rows), 'results': rows,
                      'scope': 'Small hand-authored demonstration set; not a production retrieval benchmark.'}
            if args.report:
                args.report.parent.mkdir(parents=True, exist_ok=True)
                args.report.write_text(json.dumps(result, indent=2))
            emit(result)
        elif args.command == 'serve':
            from .api import create_app
            import uvicorn
            uvicorn.run(create_app(settings), host='127.0.0.1', port=args.port)
        elif args.command == 'export-demo':
            from .snapshot import export_demo
            emit(export_demo(store, args.output))
        elif args.command == 'status':
            emit({'counts': store.counts(), 'database': 'postgresql' if store.postgres else 'sqlite',
                  'claude_configured': bool(settings.anthropic_key), 'semantic_configured': settings.semantic_ready,
                  'recap_configured': bool(settings.courtlistener_token)})
    except (ValueError, OSError, KeyError) as exc:
        print(f'CourtSignal: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
