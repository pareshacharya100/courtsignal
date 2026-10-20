"""Record docs/demo.gif: a scripted walkthrough of the local explorer.

Dev-only tooling, not a project dependency:
    python -m pip install playwright pillow && python -m playwright install chromium
    python scripts/record_demo.py            # semantic step is skipped unless Voyage/Pinecone are configured

Uses the real ingested corpus and, if configured, real Voyage/Pinecone retrieval. Nothing is simulated.
"""
from io import BytesIO
from pathlib import Path
import subprocess
import sys
import time
import httpx
from PIL import Image
from playwright.sync_api import sync_playwright

PORT = 8765
BASE = f'http://127.0.0.1:{PORT}'
OUTPUT = Path('docs/demo.gif')
WIDTH = 1000  # GIF width; capture is 1280x1000


def main():
    server = subprocess.Popen([sys.executable, '-m', 'courtsignal.cli', 'serve', '--port', str(PORT)],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            try:
                status = httpx.get(BASE + '/api/status').json()
                break
            except httpx.TransportError:
                time.sleep(0.2)
        else:
            raise SystemExit('Server did not start')
        frames = record(status['semantic_configured'])
    finally:
        server.terminate()
    save(frames)


def record(semantic):
    frames = []
    with sync_playwright() as p:
        page = p.chromium.launch().new_page(viewport={'width': 1280, 'height': 1000})

        def shot(ms=1200):
            frames.append((Image.open(BytesIO(page.screenshot())).convert('RGB'), ms))

        def search(query, mode='keyword'):
            page.select_option('#mode', mode)
            page.fill('#query', '')
            for i in range(0, len(query), 6):  # visible typing, a few frames
                page.type('#query', query[i:i + 6])
                shot(120)
            page.click('#search button[type=submit]')
            page.wait_for_selector('#results article.result')
            page.wait_for_function("!document.getElementById('message').textContent.startsWith('Searching')")
            shot(2600)

        page.goto(BASE)
        page.wait_for_selector('#cases .case')
        shot(2200)
        search('fake opinions sanctions')
        page.click('#results article.result button')
        page.wait_for_function("document.querySelector('#detail h2').textContent !== 'Context, intact.'")
        shot(3200)
        if semantic:
            search('What happened when counsel submitted invented cases?', 'semantic')
        page.locator('#cases .case', has_text='Garcia').click()
        page.wait_for_function("document.getElementById('message').textContent.includes('Document timeline')")
        shot(2200)
        page.click('#results article.result button')
        page.wait_for_function("document.querySelector('#detail h2').textContent.includes('Judicial')")
        shot(3600)
    return frames


def save(frames):
    images = [img.resize((WIDTH, round(img.height * WIDTH / img.width)), Image.LANCZOS)
              .quantize(colors=128, method=Image.Quantize.MEDIANCUT) for img, _ in frames]
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    images[0].save(OUTPUT, save_all=True, append_images=images[1:], duration=[ms for _, ms in frames],
                   loop=0, optimize=True)
    print(f'{OUTPUT}: {len(images)} frames, {OUTPUT.stat().st_size / 1e6:.1f} MB')


if __name__ == '__main__':
    main()
