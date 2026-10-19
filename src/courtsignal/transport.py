"""Bounded downloads and retries. Court records and provider responses are untrusted."""
import time
from urllib.parse import urlparse
import httpx

PUBLIC_HOSTS = {'cases.justia.com', 'docs.justia.com', 'iapps.courts.state.ny.us',
                'www.courtlistener.com', 'storage.courtlistener.com'}


def request(client, method, url, *, attempts=3, sleep=time.sleep, **kwargs):
    for attempt in range(attempts):
        try:
            response = client.request(method, url, **kwargs)
        except httpx.TransportError:
            raise ValueError(f'Network error contacting {urlparse(url).hostname}; retry explicitly') from None
        if response.status_code not in (429, 502, 503, 504) or attempt == attempts - 1:
            if response.is_error:
                # Do not expose provider error bodies, request headers or credentialed URLs.
                raise ValueError(f'HTTP {response.status_code} from {urlparse(url).hostname}')
            return response
        try:
            delay = float(response.headers.get('Retry-After', 2 ** attempt))
        except ValueError:
            delay = 2 ** attempt
        sleep(min(10, max(0, delay)))
    raise RuntimeError('Unreachable retry state')


def download_pdf(url, limit=20 * 1024 * 1024):
    with httpx.Client(timeout=45, follow_redirects=False, headers={'User-Agent': 'CourtSignal/0.1 research prototype'}) as client:
        for _ in range(5):
            parsed = urlparse(url)
            if parsed.scheme != 'https' or parsed.hostname not in PUBLIC_HOSTS or parsed.username or parsed.password or parsed.port not in (None, 443):
                raise ValueError('Download host is not an approved public court-document source')
            # Streaming enforces the limit before loading a large PDF into memory.
            with client.stream('GET', url) as response:
                if response.is_redirect:
                    from urllib.parse import urljoin
                    url = urljoin(url, response.headers['location'])
                    continue
                if response.status_code != 200:
                    raise ValueError(f'Document download returned HTTP {response.status_code}; retry later or check source access')
                data = bytearray()
                for part in response.iter_bytes():
                    data.extend(part)
                    if len(data) > limit:
                        raise ValueError('PDF exceeds the 20 MB prototype limit')
                if not data.startswith(b'%PDF-'):
                    raise ValueError('Source did not return a PDF; login pages are not indexed')
                return bytes(data)
    raise ValueError('Too many document redirects')
