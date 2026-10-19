from hashlib import sha256
import json
from pathlib import Path
import httpx
from pypdf.errors import PyPdfError
from .models import DocumentSpec
from .parsing import parse_pdf, validate_header, chunk_pages
from .transport import download_pdf


def load_manifest(path):
    values = json.loads(Path(path).read_text())
    specs = [DocumentSpec.model_validate(item) for item in values]
    if len({spec.id for spec in specs}) != len(specs):
        raise ValueError('Manifest contains duplicate document identities')
    return specs


def acquire(spec, downloader):
    """Return (bytes, retrieved_from, primary_error). Only a failed download falls back, never a changed file."""
    try:
        return downloader(spec.download_url), spec.download_url, None
    except (ValueError, httpx.TransportError) as exc:
        if not spec.fallback_url:
            raise
        # The archived copy is accepted only because ingest() checks its pinned SHA-256.
        return downloader(spec.fallback_url), spec.fallback_url, str(exc) or type(exc).__name__


def ingest(specs, store, data_dir, refresh=False, downloader=download_pdf):
    raw_dir = Path(data_dir) / 'raw'
    raw_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for spec in specs:
        try:
            previous = store.document(spec.id)
            cache = raw_dir / f'{previous["content_hash"]}.pdf' if previous else None
            if cache and cache.exists() and not refresh:
                data, retrieved_from, primary_error = cache.read_bytes(), 'local raw cache', None
            else:
                data, retrieved_from, primary_error = acquire(spec, downloader)
            digest = sha256(data).hexdigest()
            if spec.expected_sha256 and digest != spec.expected_sha256:
                raise ValueError('SHA-256 does not match the pinned source document')
            pages = parse_pdf(data)
            quality = validate_header(spec, pages)
            quality['retrieved_from'] = retrieved_from
            if primary_error:
                quality['primary_source_error'] = primary_error
            chunks = chunk_pages(spec.id, digest, pages)
            # Immutable raw files preserve the prior version if a refreshed file is rejected.
            destination = raw_dir / f'{digest}.pdf'
            temporary = destination.with_suffix('.tmp')
            temporary.write_bytes(data)
            temporary.replace(destination)
            status = store.save_document(spec, digest, pages, chunks, quality)
            result = {'document_id': spec.id, 'title': spec.title, 'status': status,
                      'pages': len(pages), 'chunks': len(chunks), 'sha256': digest, 'quality': quality}
            store.event(spec.id, status, json.dumps({'sha256': digest, 'retrieved_from': retrieved_from}))
        except (httpx.TransportError, PyPdfError):
            result = {'document_id': spec.id, 'title': spec.title, 'status': 'quarantined',
                      'error': 'Document download or PDF parsing failed; retry or inspect the public source'}
            store.event(spec.id, 'quarantined', result['error'])
        except (ValueError, OSError, RuntimeError) as exc:
            # Failed input never replaces the current canonical record.
            result = {'document_id': spec.id, 'title': spec.title, 'status': 'quarantined', 'error': str(exc)}
            store.event(spec.id, 'quarantined', str(exc))
        results.append(result)
    return {'documents': results, 'counts': store.counts()}
