const $ = id => document.getElementById(id);
let selectedCase = null;
function el(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}
async function api(path) {
  const response = await fetch(path);
  const body = await response.json();
  if (!response.ok) throw new Error(body.detail || 'Request failed');
  return body;
}
function link(text, href) {
  const node = el('a', text);
  node.href = href; node.target = '_blank'; node.rel = 'noopener noreferrer';
  return node;
}
function message(text) { $('message').textContent = text; }
async function inspect(id, page = 1) {
  try {
    const doc = await api('/api/documents/' + encodeURIComponent(id));
    const pane = $('detail'); pane.replaceChildren(el('p', 'DOCUMENT INSPECTOR', 'eyebrow'), el('h2', doc.title));
    const dl = el('dl');
    for (const [name, value] of [['Document', '#' + doc.document_number], ['Filed', doc.filed_date || 'Not provided'],
      ['Acquisition', doc.acquisition.replaceAll('_', ' ')], ['SHA-256', doc.content_hash], ['Parser', doc.parser_version]]) {
      dl.append(el('dt', name), el('dd', value));
    }
    pane.append(dl, link('Open source PDF ↗', doc.source_url + '#page=' + page));
    if (!window.COURTSIGNAL_OFFLINE) pane.append(el('br'), link('Open cached page ' + page + ' ↗', '/api/documents/' + id + '/file#page=' + page));
    const quality = doc.quality;
    pane.append(el('div', 'Document number: ' + (quality.document_number_verified ? 'matched' : 'not verified') + '\nFiling date: ' +
      (quality.filing_date_verified ? 'matched' : 'not verified') + '\nText page coverage: ' + Math.round(quality.text_page_coverage * 100) + '%', 'checks'));
    pane.append(el('h3', 'Page ' + page + ' / ' + doc.page_count));
    pane.append(el('div', doc.pages.find(p => p.number === page)?.text || 'No text extracted', 'page-text'));
  } catch (error) { message(error.message); }
}
function renderHits(hits) {
  $('results').replaceChildren();
  if (!hits.length) { $('results').append(el('p', 'No matching evidence in this corpus.')); return; }
  for (const hit of hits) {
    const card = el('article', undefined, 'result');
    card.append(el('span', hit.source_system === 'pacer' ? 'FEDERAL' : 'NYSCEF', 'tag'), el('h3', hit.title),
      el('div', hit.case_name + ' · Page ' + hit.page + ' · ' + hit.mode + ' score ' + hit.score.toFixed(2), 'meta'),
      el('p', hit.text.length > 550 ? hit.text.slice(0, 550) + '…' : hit.text));
    const button = el('button', 'Inspect evidence ↗'); button.onclick = () => inspect(hit.document_id, hit.page);
    card.append(button); $('results').append(card);
  }
}
let searchSequence = 0;
async function runSearch(event) {
  event?.preventDefault();
  const seq = ++searchSequence;
  const query = $('query').value.trim(); if (!query) return;
  message('Searching…');
  const params = new URLSearchParams({q: query, mode: $('mode').value});
  if ($('source').value) params.set('source', $('source').value);
  if (selectedCase) params.set('case_id', selectedCase);
  try {
    const result = await api('/api/search?' + params);
    if (seq !== searchSequence) return;
    message(result.results.length + ' evidence passages · ' + result.mode + ' search'); renderHits(result.results);
  } catch (error) { if (seq === searchSequence) message(error.message); }
}
async function chooseCase(item, button) {
  ++searchSequence; selectedCase = item.id;
  document.querySelectorAll('.case').forEach(n => n.classList.remove('active')); button.classList.add('active');
  message('Loading case documents…');
  try {
    const docs = await api('/api/cases/' + item.id);
    if (selectedCase !== item.id) return;
    $('results').replaceChildren(); message(item.case_name + ' · Document timeline');
    docs.forEach(doc => {
      const card = el('article', undefined, 'result');
      card.append(el('span', doc.filed_date || 'Date unknown', 'tag'), el('h3', doc.title),
        el('p', 'Document #' + doc.document_number + ' · ' + doc.page_count + ' pages · ' + doc.acquisition.replaceAll('_', ' ')));
      const open = el('button', 'Inspect document ↗'); open.onclick = () => inspect(doc.document_id); card.append(open); $('results').append(card);
    });
  } catch (error) { message(error.message); }
}
$('search').onsubmit = runSearch;
$('example').onclick = () => { $('query').value = 'fake opinions sanctions'; runSearch(); };
$('all').onclick = () => { selectedCase = null; document.querySelectorAll('.case').forEach(n => n.classList.remove('active')); message('Searching all cases'); if ($('query').value) runSearch(); };
async function init() {
  try {
    const [status, cases] = await Promise.all([api('/api/status'), api('/api/cases')]);
    $('database').textContent = status.database === 'snapshot' ? 'OFFLINE / REAL RECORDS' : status.database.toUpperCase() + ' / LOCAL';
    for (const key of ['cases', 'documents', 'pages']) {
      const metric = el('div', undefined, 'metric'); metric.append(el('strong', status.counts[key]), el('span', key)); $('metrics').append(metric);
    }
    for (const item of cases) {
      const button = el('button', undefined, 'case');
      button.append(el('span', item.source_system === 'pacer' ? 'FEDERAL · ' + item.court.toUpperCase() : 'NEW YORK · QUEENS', 'tag'),
        el('strong', item.case_name), el('small', item.docket_number + ' · ' + item.documents + ' docs'));
      button.onclick = () => chooseCase(item, button); $('cases').append(button);
    }
    if (!status.semantic_configured) $('mode').options[1].textContent += ' · setup needed';
  } catch (error) { message(error.message); }
}
init();
