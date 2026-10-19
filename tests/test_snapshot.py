from courtsignal.parsing import chunk_pages
from courtsignal.models import Page
from courtsignal.snapshot import export_demo


def test_snapshot_preserves_real_records_and_escapes_script_content(store, spec, tmp_path):
    pages = [Page(number=1, text='Court text includes an untrusted string </script><script>alert(1)</script> and enough text.')]
    store.save_document(spec, 'hash', pages, chunk_pages(spec.id, 'hash', pages), {})
    destination = tmp_path / 'demo.html'
    result = export_demo(store, destination)
    text = destination.read_text()
    assert result['counts']['documents'] == 1
    assert '</script><script>alert(1)' not in text
    assert '\\u003c/script\\u003e' in text
    assert 'window.COURTSIGNAL_OFFLINE = true' in text
    assert 'offline keyword snapshot' == result['mode']
