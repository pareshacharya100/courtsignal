// Snapshot mode uses real exported records. It never simulates an external AI service.
window.COURTSIGNAL_OFFLINE = true;
const snapshot = JSON.parse(document.getElementById('corpus').textContent);
const stopWords = new Set(['the','a','an','of','in','on','for','and','is','to','was','what','did','with']);
function tokenize(text) { return (text.toLowerCase().match(/[a-z0-9]+/g) || []).filter(t => !stopWords.has(t)); }
function offlineSearch(chunks, query, limit) {
  const terms = [...new Set(tokenize(query))];
  const counts = chunks.map(h => { const count = new Map(); for (const t of tokenize(h.text)) count.set(t,(count.get(t)||0)+1); return count; });
  const lengths = counts.map(c => [...c.values()].reduce((a,b) => a+b,0));
  const average = lengths.reduce((a,b) => a+b,0) / Math.max(chunks.length,1) || 1;
  const df = new Map(terms.map(t => [t,counts.filter(c => c.has(t)).length]));
  return chunks.map((h,i) => {
    let score = 0;
    for (const t of terms) {
      const tf = counts[i].get(t)||0;
      if (tf) score += Math.log(1+(chunks.length-df.get(t)+.5)/(df.get(t)+.5))*tf*2.2/(tf+1.2*(.25+.75*lengths[i]/average));
    }
    return {...h,score:Math.round(score*1e6)/1e6,mode:'keyword'};
  }).filter(h => h.score>0).sort((a,b) => b.score-a.score || a.id.localeCompare(b.id)).slice(0,limit);
}
window.fetch = async path => {
  const url = new URL(path,'https://offline.invalid');
  let body, status=200;
  if (url.pathname === '/api/status') body=snapshot.status;
  else if (url.pathname === '/api/cases') body=snapshot.cases;
  else if (url.pathname.startsWith('/api/cases/')) body=snapshot.timeline.filter(d => d.case_id===url.pathname.split('/').pop());
  else if (url.pathname.startsWith('/api/documents/')) {
    body=snapshot.documents[url.pathname.split('/').pop()];
    if (!body) {status=404;body={detail:'Document not found in snapshot'};}
  } else if (url.pathname === '/api/search') {
    if (url.searchParams.get('mode')==='semantic') {status=503;body={detail:'This offline snapshot supports keyword search. Run the Python application with Voyage and Pinecone for semantic search.'};}
    else {
      const source=url.searchParams.get('source'), caseId=url.searchParams.get('case_id');
      const chunks=snapshot.chunks.filter(h => (!source || h.source_system===source) && (!caseId || h.case_id===caseId));
      body={mode:'keyword',results:offlineSearch(chunks,url.searchParams.get('q')||'',Number(url.searchParams.get('limit')||5))};
    }
  } else {status=404;body={detail:'This route is unavailable offline'};}
  return {ok:status===200,status,json:async()=>body};
};
