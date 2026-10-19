"""Page-preserving parsing; scanned pages are flagged rather than silently guessed."""
from datetime import datetime
from io import BytesIO
import re
import unicodedata
from pypdf import PdfReader
from .models import Chunk, DocumentSpec, Page, stable_id

PARSER_VERSION = 'pypdf-pages-v2'


def normalize(text: str) -> str:
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFKC', text)).strip()


def parse_pdf(data: bytes) -> list[Page]:
    if not data.startswith(b'%PDF-'):
        raise ValueError('Expected PDF bytes; received an HTML/login page or unsupported file')
    reader = PdfReader(BytesIO(data))
    if reader.is_encrypted:
        raise ValueError('Encrypted PDF is not supported')
    if len(reader.pages) > 500:
        raise ValueError('Prototype limit is 500 pages per document')
    return [Page(number=i + 1, text=normalize(page.extract_text() or '')) for i, page in enumerate(reader.pages)]


def validate_header(spec: DocumentSpec, pages: list[Page]) -> dict:
    if not pages:
        raise ValueError('PDF contains no pages')
    first = pages[0].text
    number = re.search(r'NYSCEF\s+DOC\.?\s*NO\.?\s*(\d+)', first, re.I) if spec.case.source_system == 'nyscef' else re.search(r'\bDocument\s+(\d+)\s+Filed\b', first, re.I)
    if number and number.group(1) != spec.document_number:
        raise ValueError(f'Document-number mismatch: manifest {spec.document_number}, header {number.group(1)}')
    case_match = (re.search(r'\bINDEX\s+NO\.?\s*(\d+/\d{4})', first, re.I)
                  if spec.case.source_system == 'nyscef' else
                  re.search(r'\bCase\s+(\d+:\d{2}-[a-z]{1,3}-\d+)', first, re.I))
    if case_match and case_match.group(1).lower() != spec.case.docket_number.lower():
        raise ValueError('Case-number mismatch between manifest and court stamp')
    match = re.search(r'\bFiled\s+(\d{2}/\d{2}/\d{2,4})\b', first, re.I)
    if spec.case.source_system == 'nyscef':
        # Match the clerk stamp, not a form field such as "If yes, date filed:".
        match = re.search(r'\bFILED:\s+[A-Z ]{2,60}CLERK\s+(\d{2}/\d{2}/\d{4})\b', first, re.I)
    date_verified = False
    if match and spec.filed_date:
        value = match.group(1)
        extracted = datetime.strptime(value, '%m/%d/%Y' if len(value) == 10 else '%m/%d/%y').date()
        if extracted != spec.filed_date:
            raise ValueError(f'Filing-date mismatch: manifest {spec.filed_date}, header {extracted}')
        date_verified = True
    empty = [p.number for p in pages if len(p.text) < 30]
    if len(empty) == len(pages):
        raise ValueError('No usable text: OCR required before indexing')
    return {'document_number_verified': bool(number), 'case_number_verified': bool(case_match), 'filing_date_verified': date_verified,
            'page_count': len(pages), 'needs_ocr_pages': empty,
            'text_page_coverage': round((len(pages) - len(empty)) / len(pages), 4)}


def chunk_pages(document_id: str, content_hash: str, pages: list[Page], size=1600, overlap=180):
    if not 0 <= overlap < size:
        raise ValueError('overlap must be nonnegative and smaller than chunk size')
    chunks = []
    for page in pages:
        if len(page.text) < 30:
            continue
        start = 0
        while start < len(page.text):
            end = min(start + size, len(page.text))
            if end < len(page.text):
                boundary = page.text.rfind(' ', start + size // 2, end)
                if boundary > start:
                    end = boundary
            text = page.text[start:end]
            chunks.append(Chunk(id=stable_id(document_id, content_hash, PARSER_VERSION, str(page.number), str(start), str(end)),
                                document_id=document_id, page=page.number, char_start=start, char_end=end, text=text))
            if end == len(page.text):
                break
            start = max(start + 1, end - overlap)
    return chunks


def validate_facts(facts, pages):
    lookup = {p.number: p.text for p in pages}
    for fact in facts:
        if fact.page not in lookup or normalize(fact.quote) not in normalize(lookup[fact.page]):
            raise ValueError(f'Unsupported evidence for {fact.field} on page {fact.page}')
    # This validates quote presence, NOT whether the quote entails the model's claim.
    return facts
