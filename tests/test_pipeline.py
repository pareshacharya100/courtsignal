from datetime import date
from hashlib import sha256
from io import BytesIO
import pytest
from pypdf import PdfWriter
from courtsignal.models import Case, DocumentSpec, Page, Fact, Extraction
from courtsignal.parsing import chunk_pages, parse_pdf, validate_header, validate_facts
from courtsignal.pipeline import ingest


def test_case_identity_includes_court(spec):
    assert spec.case.id != spec.case.model_copy(update={'court': 'nyed'}).id
    assert spec.id != spec.model_copy(update={'attachment_number': '1'}).id


def test_chunk_spans_and_high_overlap_make_progress():
    text = ('several words with different lengths ' * 15).strip()
    page = Page(number=2, text=text)
    chunks = chunk_pages('doc', 'hash', [page], size=50, overlap=45)
    assert chunks and len(chunks) <= len(text)
    assert all(c.text == text[c.char_start:c.char_end] and c.page == 2 for c in chunks)
    assert chunks[-1].char_end == len(text)
    assert len({c.id for c in chunks}) == len(chunks)
    assert chunks[0].id != chunk_pages('doc', 'changed', [page], size=50, overlap=45)[0].id


@pytest.mark.parametrize('field,value', [('document_number', '55'), ('filed_date', date(2023, 6, 21))])
def test_wrong_manifest_metadata_rejected(spec, pages, field, value):
    with pytest.raises(ValueError, match='mismatch'):
        validate_header(spec.model_copy(update={field: value}), pages)


def test_wrong_case_rejected(spec, pages):
    wrong = spec.model_copy(update={'case': spec.case.model_copy(update={'docket_number': '1:22-cv-09999'})})
    with pytest.raises(ValueError, match='Case-number mismatch'):
        validate_header(wrong, pages)


def test_nyscef_service_date_is_not_filing_date(spec):
    spec = spec.model_copy(update={'case': Case(source_system='nyscef', court='queens', docket_number='701695/2024', case_name='Garcia'),
                                  'document_number': '35', 'filed_date': date(2024, 9, 23)})
    page = Page(number=1, text='If yes, date filed: If yes, date served: 06/23/2024 '
                'FILED: QUEENS COUNTY CLERK 09/23/2024 05:27 PM INDEX NO. 701695/2024 NYSCEF DOC. NO. 35')
    assert validate_header(spec, [page])['filing_date_verified'] is True


def test_scanned_pdf_requires_ocr(spec):
    writer = PdfWriter(); writer.add_blank_page(width=300, height=300)
    buffer = BytesIO(); writer.write(buffer)
    pages = parse_pdf(buffer.getvalue())
    with pytest.raises(ValueError, match='OCR required'):
        validate_header(spec, pages)
    assert not chunk_pages(spec.id, 'hash', pages)


def test_html_login_page_rejected():
    with pytest.raises(ValueError, match='Expected PDF'):
        parse_pdf(b'<html>Sign in to view</html>')


def test_hallucinated_quote_and_page_rejected(pages):
    fact = Fact(field='judge', value='Example', page=1, quote='This quote is not in the document')
    with pytest.raises(ValueError, match='Unsupported evidence'):
        validate_facts([fact], pages)
    fact = Fact(field='disposition', value='Sanctions', page=99, quote='The court imposed sanctions')
    with pytest.raises(ValueError):
        validate_facts([fact], pages)


def test_idempotent_rerun_and_changed_document_invalidate_extraction(store, spec, pages):
    quality = validate_header(spec, pages)
    chunks = chunk_pages(spec.id, 'first', pages)
    assert store.save_document(spec, 'first', pages, chunks, quality) == 'created'
    store.save_extraction(spec.id, 'first', 'mock-model', {'pages': [1]}, Extraction())
    counts = store.counts()
    assert store.save_document(spec, 'first', pages, chunks, quality) == 'unchanged'
    assert store.counts() == counts
    new_chunks = chunk_pages(spec.id, 'second', pages)
    assert store.save_document(spec, 'second', pages, new_chunks, quality) == 'updated'
    assert store.counts()['extractions'] == 0
    assert {c['id'] for c in store.chunks()} == {c.id for c in new_chunks}
    with pytest.raises(ValueError, match='changed'):
        store.save_extraction(spec.id, 'first', 'mock-model', {}, Extraction())


def test_failed_refresh_preserves_existing_record(store, spec, pages, tmp_path):
    store.save_document(spec, 'old', pages, chunk_pages(spec.id, 'old', pages), validate_header(spec, pages))
    result = ingest([spec], store, tmp_path, refresh=True, downloader=lambda _: b'<html>Login</html>')
    assert result['documents'][0]['status'] == 'quarantined'
    assert store.document(spec.id)['content_hash'] == 'old'
    assert store.counts()['pages'] == 1


def test_failed_child_insert_rolls_back_document_replacement(store, spec, pages):
    store.save_document(spec, 'old', pages, chunk_pages(spec.id, 'old', pages), {})
    duplicate = chunk_pages(spec.id, 'new', pages)[0]
    with pytest.raises(Exception):
        store.save_document(spec, 'new', pages, [duplicate, duplicate], {})
    assert store.document(spec.id)['content_hash'] == 'old'
    assert store.chunks()[0]['id'] != duplicate.id


def test_blocked_source_falls_back_to_pinned_archive_copy(store, spec, pages, tmp_path, monkeypatch):
    import courtsignal.pipeline as module
    data = b'%PDF-archived court document'
    archive = 'https://github.com/example/courtsignal/releases/download/corpus-v1/doc.pdf'
    pinned = spec.model_copy(update={'expected_sha256': sha256(data).hexdigest(), 'fallback_url': archive})
    monkeypatch.setattr(module, 'parse_pdf', lambda _: pages)
    def downloader(url):
        if url == spec.download_url:
            raise ValueError('Document download returned HTTP 403; retry later or check source access')
        return data
    result = ingest([pinned], store, tmp_path, downloader=downloader)['documents'][0]
    assert result['status'] == 'created'
    assert result['quality']['retrieved_from'] == archive
    assert 'HTTP 403' in result['quality']['primary_source_error']
    assert store.document(spec.id)['source_url'] == spec.download_url  # canonical source is unchanged


def test_fallback_copy_must_match_pin(store, spec, tmp_path):
    pinned = spec.model_copy(update={'expected_sha256': '0' * 64, 'fallback_url': 'https://github.com/example/doc.pdf'})
    def downloader(url):
        if url == spec.download_url:
            raise ValueError('HTTP 403')
        return b'%PDF-tampered copy'
    result = ingest([pinned], store, tmp_path, downloader=downloader)['documents'][0]
    assert result['status'] == 'quarantined' and 'SHA-256' in result['error']
    assert store.counts()['documents'] == 0


def test_fallback_requires_pinned_hash(spec):
    with pytest.raises(ValueError, match='pinned'):
        DocumentSpec.model_validate({**spec.model_dump(mode='json'), 'fallback_url': 'https://github.com/example/doc.pdf'})


def test_checksum_mismatch_is_quarantined_before_parsing(store, spec, tmp_path):
    pinned = spec.model_copy(update={'expected_sha256': '0' * 64})
    result = ingest([pinned], store, tmp_path, downloader=lambda _: b'%PDF-wrong')
    assert 'SHA-256' in result['documents'][0]['error']
    assert store.counts()['documents'] == 0
