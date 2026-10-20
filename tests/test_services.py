from hashlib import sha256
import json
import httpx
import pytest
from courtsignal.config import Settings
from courtsignal.models import Page
from courtsignal.providers import Claude, Voyage, Pinecone
from courtsignal.sources import RecapSource
from courtsignal.transport import browser_download, request, download_pdf


def client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_retry_after_is_bounded_and_errors_are_redacted():
    calls = []; delays = []
    def handler(req):
        calls.append(req)
        return httpx.Response(429 if len(calls) == 1 else 200, headers={'Retry-After': '999'}, json={})
    assert request(client(handler), 'GET', 'https://example.test/', sleep=delays.append).status_code == 200
    assert delays == [10]
    with pytest.raises(ValueError, match='HTTP 401') as exc:
        request(client(lambda _: httpx.Response(401, text='secret-key-response')), 'GET', 'https://example.test/')
    assert 'secret-key-response' not in str(exc.value)


def test_document_download_does_not_allow_arbitrary_hosts():
    with pytest.raises(ValueError, match='approved'):
        download_pdf('https://example.org/not-a-court.pdf')


NYSCEF = 'https://iapps.courts.state.ny.us/nyscef/ViewDocument?docIndex=test'


def test_browser_download_waits_for_file_matching_pin(tmp_path):
    data = b'%PDF-court filing'
    (tmp_path / 'unrelated.pdf').write_bytes(b'%PDF-something else')
    opened, ticks = [], iter(range(100))
    def opener(url):
        opened.append(url)
        return True
    def sleep(_):
        if next(ticks) == 2:  # the browser finishes saving after a few polls
            (tmp_path / 'ViewDocument.pdf').write_bytes(data)
    path, found = browser_download(NYSCEF, sha256(data).hexdigest(), tmp_path, timeout=60,
                                   opener=opener, sleep=sleep, clock=lambda: 0)
    assert opened == [NYSCEF] and found == data and path.name == 'ViewDocument.pdf'


def test_browser_download_reuses_existing_file_without_opening(tmp_path):
    data = b'%PDF-already downloaded'
    (tmp_path / 'saved.pdf').write_bytes(data)
    path, _ = browser_download(NYSCEF, sha256(data).hexdigest(), tmp_path, opener=lambda _: pytest.fail('Browser opened'))
    assert path.name == 'saved.pdf'


def test_browser_download_times_out_and_rejects_unapproved_hosts(tmp_path):
    clock = iter([0, 0, 5, 11])
    with pytest.raises(ValueError, match='No PDF matching'):
        browser_download(NYSCEF, '0' * 64, tmp_path, timeout=10, opener=lambda _: True,
                         sleep=lambda _: None, clock=lambda: next(clock))
    with pytest.raises(ValueError, match='approved'):
        browser_download('https://example.org/x.pdf', '0' * 64, tmp_path, opener=lambda _: pytest.fail('Browser opened'))


def test_claude_schema_constraints_and_evidence_are_checked(pages):
    def handler(req):
        body = json.loads(req.content)
        schema = json.dumps(body['output_config']['format']['schema'])
        assert 'minLength' not in schema and 'maxItems' not in schema
        return httpx.Response(200, json={'stop_reason': 'end_turn', 'content': [{'type': 'text', 'text': json.dumps({
            'facts': [{'field': 'disposition', 'value': 'Sanctions imposed', 'page': 1, 'quote': 'The court imposed sanctions'}]})}]})
    result = Claude(Settings(anthropic_key='test'), client(handler)).extract(pages)
    assert result.facts[0].page == 1
    with pytest.raises(ValueError, match='Unsupported evidence'):
        Claude(Settings(anthropic_key='test'), client(handler)).extract([Page(number=1, text='This page has no matching evidence whatsoever.')])


def test_claude_rejects_truncation_without_retry(pages):
    calls = []
    def handler(req):
        calls.append(req)
        return httpx.Response(200, json={'stop_reason': 'max_tokens', 'content': []})
    with pytest.raises(ValueError, match='incomplete'):
        Claude(Settings(anthropic_key='test'), client(handler)).extract(pages)
    assert len(calls) == 1


@pytest.mark.parametrize('vector', [[1.0], [1.0, 'invalid']])
def test_invalid_embedding_is_rejected(tmp_path, vector):
    service = Voyage(Settings(data_dir=tmp_path, voyage_key='test', embedding_dimension=2),
        client(lambda _: httpx.Response(200, json={'data': [{'index': 0, 'embedding': vector}]})))
    with pytest.raises(ValueError, match='Embedding'):
        service.embed(['text'], 'document')


def test_embedding_input_type_and_cache_separation(tmp_path):
    calls = []
    def handler(req):
        calls.append(json.loads(req.content))
        return httpx.Response(200, json={'data': [{'index': 0, 'embedding': [1.0, 0.0]}]})
    voyage = Voyage(Settings(data_dir=tmp_path, voyage_key='test', embedding_dimension=2), client(handler))
    assert voyage.embed(['same text'], 'document') == [[1.0, 0.0]]
    voyage.embed(['same text'], 'document')
    voyage.embed(['same text'], 'query')
    assert len(calls) == 2
    assert [c['input_type'] for c in calls] == ['document', 'query']
    assert all(c['truncation'] is False for c in calls)


def test_embedding_batches_are_paced(tmp_path):
    sizes, pauses = [], []
    def handler(req):
        inputs = json.loads(req.content)['input']
        sizes.append(len(inputs))
        return httpx.Response(200, json={'data': [{'index': i, 'embedding': [1.0, 0.0]} for i in range(len(inputs))]})
    voyage = Voyage(Settings(data_dir=tmp_path, voyage_key='test', embedding_dimension=2), client(handler))
    voyage.embed([f'text {i}' for i in range(5)], 'document', batch_size=2, pause=21, sleep=pauses.append)
    assert sizes == [2, 2, 1] and pauses == [21, 21]


def test_pinecone_model_dimension_and_source_filter():
    def handler(req):
        assert req.headers['X-Pinecone-Api-Version'] == '2025-10'
        body = json.loads(req.content)
        assert body['filter']['model']['$eq'] == 'voyage-4-lite'
        assert body['filter']['dimension']['$eq'] == 1024
        assert body['filter']['source_system']['$eq'] == 'nyscef'
        assert body['filter']['case_id']['$eq'] == 'case'
        return httpx.Response(200, json={'matches': []})
    service = Pinecone(Settings(pinecone_key='test', pinecone_host='https://sample.svc.pinecone.io'), client(handler))
    assert service.query([1.0], source='nyscef', case_id='case') == []


def test_wrong_pinecone_host_rejected():
    with pytest.raises(ValueError, match='valid HTTPS'):
        Pinecone(Settings(pinecone_key='test', pinecone_host='https://pinecone.io.evil.test'))


def test_recap_pagination_available_documents_only():
    def handler(req):
        assert req.headers['Authorization'] == 'Token test'
        if '/dockets/' in req.url.path:
            return httpx.Response(200, json={'court_id': 'nysd', 'docket_number': '1:22-cv-01461', 'case_name': 'Mata'})
        if req.url.params.get('cursor'):
            return httpx.Response(200, json={'next': None, 'results': [{'entry_number': 54, 'date_filed': '2023-06-22', 'recap_documents': [
                {'document_number': '54', 'is_available': True, 'filepath_local': 'recap/gov.uscourts.test.54.0.pdf'}]}]})
        return httpx.Response(200, json={'next': 'https://www.courtlistener.com/api/rest/v4/docket-entries/?cursor=next', 'results': [
            {'entry_number': 1, 'recap_documents': [{'is_available': False}]}]})
    docs = RecapSource('test', client(handler)).documents(123)
    assert len(docs) == 1 and docs[0].acquisition == 'recap_api'
    assert docs[0].download_url.startswith('https://storage.courtlistener.com/recap/')


def test_recap_token_cannot_follow_offsite_pagination():
    source = RecapSource('test', client(lambda _: pytest.fail('Credential leaked to network')))
    with pytest.raises(ValueError, match='outside'):
        source.get('https://example.test/api/rest/v4/dockets/1/')


@pytest.mark.parametrize('chunk_id,quote', [('not-retrieved', 'The court imposed sanctions'), ('valid', 'This was never stated by the court')])
def test_rag_answer_rejects_fabricated_citations(chunk_id, quote):
    payload = {'claims': [{'text': 'Sanctions imposed', 'chunk_id': chunk_id, 'quote': quote}], 'abstained': False}
    service = Claude(Settings(anthropic_key='test'), client(lambda _: httpx.Response(200, json={
        'stop_reason': 'end_turn', 'content': [{'type': 'text', 'text': json.dumps(payload)}]})))
    with pytest.raises(ValueError, match='valid retrieved quote'):
        service.answer('What happened?', [{'id': 'valid', 'text': 'The court imposed sanctions', 'case_name': 'Mata', 'page': 1}])


def test_rag_no_evidence_abstains_without_network():
    service = Claude(Settings(anthropic_key='test'), client(lambda _: pytest.fail('No evidence should not call Claude')))
    assert service.answer('An unsupported question', []).abstained
