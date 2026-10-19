"""Explicit keyword baseline and Voyage/Pinecone retrieval over canonical chunks."""
from collections import Counter
import math
import re
from .providers import Voyage, Pinecone

STOP = {'the', 'a', 'an', 'of', 'in', 'on', 'for', 'and', 'is', 'to', 'was', 'what', 'did', 'with'}


def tokens(text):
    return [token for token in re.findall(r'[a-z0-9]+', text.lower()) if token not in STOP]


def keyword_search(chunks, question, limit=5):
    terms = set(tokens(question))
    if not terms or not chunks:
        return []
    counts = [Counter(tokens(h['text'])) for h in chunks]
    lengths = [sum(c.values()) for c in counts]
    average = sum(lengths) / len(lengths) or 1
    df = {term: sum(term in c for c in counts) for term in terms}
    results = []
    for chunk, count, length in zip(chunks, counts, lengths):
        score = 0.0
        for term in terms:
            tf = count[term]
            if tf:
                idf = math.log(1 + (len(chunks) - df[term] + 0.5) / (df[term] + 0.5))
                score += idf * tf * 2.2 / (tf + 1.2 * (0.25 + 0.75 * length / average))
        if score > 0:
            results.append({**chunk, 'score': round(score, 6), 'mode': 'keyword'})
    return sorted(results, key=lambda h: (-h['score'], h['id']))[:limit]


def search(store, settings, question, mode='keyword', limit=5, source=None, case_id=None):
    if not question.strip() or len(question) > 2000 or not 1 <= limit <= 50:
        raise ValueError('Provide a nonempty question under 2000 characters and a limit between 1 and 50')
    if source not in (None, 'pacer', 'nyscef'):
        raise ValueError('Unknown source system')
    chunks = store.chunks(source=source, case_id=case_id)
    if mode == 'keyword':
        return keyword_search(chunks, question, limit)
    if mode != 'semantic':
        raise ValueError('Search mode must be keyword or semantic')
    if not settings.semantic_ready:
        raise ValueError('Semantic search needs Voyage and Pinecone keys, an index host, and a completed index command')
    if not chunks:
        return []
    vector = Voyage(settings).embed([question], 'query')[0]
    matches = Pinecone(settings).query(vector, min(100, limit * 5), source, case_id)
    lookup = {h['id']: h for h in chunks}
    # An old vector can never revive a replaced SQL chunk or bypass source/case filters.
    return [{**lookup[m['id']], 'score': m['score'], 'mode': 'semantic'}
            for m in matches if m['id'] in lookup][:limit]
