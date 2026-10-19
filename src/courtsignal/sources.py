"""Acquire existing RECAP records. This adapter never purchases PACER documents."""
from urllib.parse import urljoin, urlparse
import httpx
from .models import Case, DocumentSpec
from .transport import request

API = 'https://www.courtlistener.com/api/rest/v4/'


class RecapSource:
    def __init__(self, token, client=None):
        if not token:
            raise ValueError('Set COURTLISTENER_TOKEN to read the RECAP API')
        self.token = token
        self.client = client or httpx.Client(timeout=45)

    def get(self, url):
        parsed = urlparse(url)
        if parsed.scheme != 'https' or parsed.hostname != 'www.courtlistener.com' or parsed.port not in (None, 443) or parsed.username or parsed.password or not parsed.path.startswith('/api/rest/v4/'):
            raise ValueError('Refusing to send CourtListener token outside its API')
        return request(self.client, 'GET', url, headers={'Authorization': f'Token {self.token}'}).json()

    def documents(self, docket_id, limit=5, max_pages=3):
        if docket_id < 1 or not 1 <= limit <= 50 or not 1 <= max_pages <= 10:
            raise ValueError('Use a positive docket ID, 1–50 documents, and 1–10 API pages')
        docket = self.get(f'{API}dockets/{docket_id}/')
        case = Case(source_system='pacer', court=docket.get('court_id') or docket['court'].rstrip('/').split('/')[-1],
                    docket_number=docket['docket_number'], case_name=docket['case_name'])
        url = f'{API}docket-entries/?docket={docket_id}&order_by=entry_number'
        output = []
        for _ in range(max_pages):
            response = self.get(url)
            for entry in response['results']:
                for document in entry.get('recap_documents', []):
                    if not document.get('is_available') or not document.get('filepath_local'):
                        continue
                    path = document['filepath_local']
                    download_url = path if path.startswith('https://') else urljoin('https://storage.courtlistener.com/', path.lstrip('/'))
                    output.append(DocumentSpec(case=case, document_number=str(document.get('document_number') or entry['entry_number']),
                        attachment_number=str(document.get('attachment_number') or '0'),
                        title=document.get('description') or entry.get('description') or 'Court filing',
                        filed_date=entry.get('date_filed'), download_url=download_url, acquisition='recap_api'))
                    if len(output) >= limit:
                        return output
            url = response.get('next')
            if not url:
                break
        return output
