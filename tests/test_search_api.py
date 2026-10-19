from fastapi.testclient import TestClient
from courtsignal.api import create_app
from courtsignal.config import Settings
from courtsignal.parsing import chunk_pages
from courtsignal.search import keyword_search, search


def test_keyword_baseline_ranks_relevant_passage():
    rows = [{'id': 'a', 'text': 'The court granted sanctions for fake opinions'},
            {'id': 'b', 'text': 'A request for judicial intervention'},
            {'id': 'c', 'text': 'The Montreal Convention time limit'}]
    assert keyword_search(rows, 'fake opinions sanctions')[0]['id'] == 'a'
    assert keyword_search(rows, 'quantum computing') == []


def test_api_provenance_filters_and_missing_semantic_config(store, spec, pages, tmp_path):
    store.save_document(spec, 'hash', pages, chunk_pages(spec.id, 'hash', pages), {})
    app = TestClient(create_app(Settings(database_url=store.url, data_dir=tmp_path)))
    status = app.get('/api/status').json()
    assert status['counts']['documents'] == 1
    assert status['semantic_configured'] is False
    results = app.get('/api/search', params={'q': 'fake opinions'}).json()['results']
    assert results[0]['source_url'] == spec.download_url
    assert results[0]['page'] == 1
    assert app.get('/api/search', params={'q': 'fake', 'source': 'nyscef'}).json()['results'] == []
    assert app.get('/api/search', params={'q': 'fake', 'mode': 'semantic'}).status_code == 503
    assert app.get('/api/search', params={'q': 'fake', 'mode': 'pretend'}).status_code == 422
    assert app.get('/api/search', params={'q': 'fake', 'limit': 1000}).status_code == 422
    assert app.get('/api/documents/missing/file').status_code == 404
    assert app.get('/api/documents/' + spec.id).json()['content_hash'] == 'hash'
    assert app.get('/').status_code == 200


def test_semantic_search_drops_old_vector_ids(store, spec, pages, monkeypatch, tmp_path):
    import courtsignal.search as module
    chunks = chunk_pages(spec.id, 'current', pages)
    store.save_document(spec, 'current', pages, chunks, {})
    class Embeddings:
        def __init__(self, _): pass
        def embed(self, texts, input_type): return [[1.0]]
    class Vectors:
        def __init__(self, _): pass
        def query(self, *args):
            return [{'id': 'stale', 'score': .99}, {'id': chunks[0].id, 'score': .8}]
    monkeypatch.setattr(module, 'Voyage', Embeddings)
    monkeypatch.setattr(module, 'Pinecone', Vectors)
    settings = Settings(data_dir=tmp_path, voyage_key='test', pinecone_key='test', pinecone_host='https://sample.svc.pinecone.io')
    hits = search(store, settings, 'fake opinions', 'semantic')
    assert len(hits) == 1 and hits[0]['id'] == chunks[0].id
