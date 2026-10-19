import json
from pathlib import Path
from typing import Literal
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from .config import Settings
from .storage import Store
from .search import search


def create_app(settings=None):
    settings = settings or Settings.from_env()
    store = Store(settings.database_url)
    app = FastAPI(title='CourtSignal', description='Read-only court-record explorer with evidence provenance')
    static = Path(__file__).parent / 'static'
    app.mount('/static', StaticFiles(directory=static), name='static')

    @app.get('/')
    def home():
        return FileResponse(static / 'index.html')

    @app.get('/api/status')
    def status():
        return {'counts': store.counts(), 'database': 'postgresql' if store.postgres else 'sqlite',
                'providers': {'claude': bool(settings.anthropic_key), 'voyage': bool(settings.voyage_key),
                              'pinecone': bool(settings.pinecone_key and settings.pinecone_host)},
                'semantic_configured': settings.semantic_ready}

    @app.get('/api/cases')
    def cases():
        return store.query('''SELECT c.*, COUNT(d.id) AS documents FROM cases c
            LEFT JOIN documents d ON c.id=d.case_id GROUP BY c.id, c.source_system, c.court, c.docket_number, c.case_name
            ORDER BY c.source_system, c.case_name''')

    @app.get('/api/cases/{case_id}')
    def timeline(case_id: str):
        return store.query('SELECT * FROM case_timeline WHERE case_id=? ORDER BY filed_date, document_number', (case_id,))

    @app.get('/api/search')
    def retrieve(q: str = Query(min_length=1, max_length=2000), mode: Literal['keyword', 'semantic'] = 'keyword',
                 source: Literal['pacer', 'nyscef'] | None = None, case_id: str | None = None,
                 limit: int = Query(5, ge=1, le=50)):
        try:
            return {'mode': mode, 'results': search(store, settings, q, mode, limit, source, case_id)}
        except ValueError as exc:
            raise HTTPException(status_code=503 if mode == 'semantic' else 400, detail=str(exc)) from None

    @app.get('/api/documents/{document_id}')
    def document(document_id: str):
        doc = store.document(document_id)
        if not doc:
            raise HTTPException(404, 'Document not found')
        doc['quality'] = json.loads(doc['quality'])
        doc.pop('spec')
        doc['pages'] = store.query('SELECT number, text FROM pages WHERE document_id=? ORDER BY number', (document_id,))
        extractions = store.query('SELECT * FROM extractions WHERE document_id=?', (document_id,))
        doc['extraction'] = extractions[0] if extractions else None
        return doc

    @app.get('/api/documents/{document_id}/file')
    def pdf(document_id: str):
        doc = store.document(document_id)
        if not doc:
            raise HTTPException(404, 'Document not found')
        path = settings.data_dir / 'raw' / f'{doc["content_hash"]}.pdf'
        if not path.exists():
            raise HTTPException(404, 'Raw file not cached; rerun ingestion')
        return FileResponse(path, media_type='application/pdf', headers={'Content-Disposition': 'inline'})

    return app
