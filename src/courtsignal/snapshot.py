"""Export the ingested corpus to a self-contained, read-only interview demo."""
import json
from pathlib import Path


def export_demo(store, destination):
    static = Path(__file__).parent / 'static'
    documents = {}
    for row in store.query('SELECT id FROM documents'):
        doc = store.document(row['id'])
        doc.pop('spec')
        doc['quality'] = json.loads(doc['quality'])
        doc['pages'] = store.query('SELECT number, text FROM pages WHERE document_id=? ORDER BY number', (doc['id'],))
        doc['extraction'] = None  # No model output is implied by a static export.
        documents[doc['id']] = doc
    corpus = {'status': {'counts': store.counts(), 'database': 'snapshot', 'semantic_configured': False},
              'cases': store.query('''SELECT c.*, COUNT(d.id) AS documents FROM cases c
                LEFT JOIN documents d ON c.id=d.case_id GROUP BY c.id, c.source_system, c.court, c.docket_number, c.case_name'''),
              'timeline': store.query('SELECT * FROM case_timeline ORDER BY filed_date, document_number'),
              'documents': documents, 'chunks': store.chunks()}
    # Escape HTML delimiters so court text can never terminate the inert JSON script.
    encoded = json.dumps(corpus).replace('&', '\\u0026').replace('<', '\\u003c').replace('>', '\\u003e')
    html = (static / 'index.html').read_text().replace('<link rel="stylesheet" href="/static/style.css">',
            '<style>' + (static / 'style.css').read_text() + '</style>')
    scripts = '<script id="corpus" type="application/json">' + encoded + '</script><script>'
    scripts += (static / 'offline.js').read_text() + '\n' + (static / 'app.js').read_text() + '</script>'
    html = html.replace('<script src="/static/app.js" defer></script>', scripts)
    html = html.replace('Research prototype · Keyword search works locally.', 'Offline corpus snapshot · Keyword search runs in your browser.')
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(html)
    return {'output': str(destination), 'counts': store.counts(), 'mode': 'offline keyword snapshot'}
