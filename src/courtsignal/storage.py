"""Transactional canonical store. SQLite for zero-service demos, PostgreSQL for deployment."""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from .parsing import PARSER_VERSION


def now():
    return datetime.now(timezone.utc).isoformat()


SCHEMA = [
    '''CREATE TABLE IF NOT EXISTS cases (
       id TEXT PRIMARY KEY, source_system TEXT NOT NULL, court TEXT NOT NULL,
       docket_number TEXT NOT NULL, case_name TEXT NOT NULL)''',
    '''CREATE TABLE IF NOT EXISTS documents (
       id TEXT PRIMARY KEY, case_id TEXT NOT NULL REFERENCES cases(id),
       document_number TEXT NOT NULL, attachment_number TEXT NOT NULL, title TEXT NOT NULL,
       filed_date TEXT, source_url TEXT NOT NULL, acquisition TEXT NOT NULL,
       content_hash TEXT NOT NULL, parser_version TEXT NOT NULL, retrieved_at TEXT NOT NULL,
       page_count INTEGER NOT NULL, quality TEXT NOT NULL, spec TEXT NOT NULL)''',
    '''CREATE TABLE IF NOT EXISTS pages (
       document_id TEXT NOT NULL REFERENCES documents(id), number INTEGER NOT NULL,
       text TEXT NOT NULL, PRIMARY KEY(document_id, number))''',
    '''CREATE TABLE IF NOT EXISTS chunks (
       id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id),
       page INTEGER NOT NULL, char_start INTEGER NOT NULL, char_end INTEGER NOT NULL, text TEXT NOT NULL)''',
    '''CREATE TABLE IF NOT EXISTS extractions (
       document_id TEXT PRIMARY KEY REFERENCES documents(id), content_hash TEXT NOT NULL,
       model TEXT NOT NULL, created_at TEXT NOT NULL, scope TEXT NOT NULL, result TEXT NOT NULL)''',
    '''CREATE TABLE IF NOT EXISTS ingestion_events (
       id TEXT PRIMARY KEY, document_id TEXT NOT NULL, occurred_at TEXT NOT NULL,
       status TEXT NOT NULL, detail TEXT NOT NULL)''',
    'CREATE INDEX IF NOT EXISTS chunks_document_idx ON chunks(document_id)',
    '''CREATE VIEW IF NOT EXISTS case_timeline AS
       SELECT c.id AS case_id, c.source_system, c.court, c.docket_number, c.case_name,
       d.id AS document_id, d.document_number, d.title, d.filed_date, d.page_count,
       d.acquisition, d.source_url FROM cases c JOIN documents d ON c.id=d.case_id''',
]


class Store:
    def __init__(self, url):
        self.url = url
        self.postgres = url.startswith(('postgresql://', 'postgres://'))
        if not self.postgres:
            if not url.startswith('sqlite:///'):
                raise ValueError('DATABASE_URL must use sqlite:/// or postgresql://')
            self.path = url.removeprefix('sqlite:///')
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            for statement in SCHEMA:
                if self.postgres and statement.startswith('CREATE VIEW IF NOT EXISTS'):
                    statement = statement.replace('CREATE VIEW IF NOT EXISTS', 'CREATE OR REPLACE VIEW', 1)
                self.execute(db, statement)

    @contextmanager
    def connection(self):
        if self.postgres:
            import psycopg
            from psycopg.rows import dict_row
            db = psycopg.connect(self.url, row_factory=dict_row)
        else:
            db = sqlite3.connect(self.path, timeout=20)
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA foreign_keys=ON')
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def execute(self, db, sql, args=()):
        return db.execute(sql.replace('?', '%s') if self.postgres else sql, args)

    def query(self, sql, args=()):
        with self.connection() as db:
            return [dict(row) for row in self.execute(db, sql, args).fetchall()]

    def document(self, document_id):
        rows = self.query('SELECT * FROM documents WHERE id=?', (document_id,))
        return rows[0] if rows else None

    def save_document(self, spec, content_hash, pages, chunks, quality):
        # A document, its pages and chunks become visible together, or not at all.
        with self.connection() as db:
            old = self.execute(db, 'SELECT * FROM documents WHERE id=?', (spec.id,)).fetchone()
            unchanged = old and old['content_hash'] == content_hash and old['parser_version'] == PARSER_VERSION and old['spec'] == spec.model_dump_json()
            if unchanged:
                return 'unchanged'
            self.execute(db, '''INSERT INTO cases VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET case_name=excluded.case_name''',
                         (spec.case.id, spec.case.source_system, spec.case.court, spec.case.docket_number, spec.case.case_name))
            if old:
                for table in ('extractions', 'chunks', 'pages'):
                    self.execute(db, f'DELETE FROM {table} WHERE document_id=?', (spec.id,))
            values = (spec.id, spec.case.id, spec.document_number, spec.attachment_number, spec.title,
                      spec.filed_date.isoformat() if spec.filed_date else None, spec.download_url,
                      spec.acquisition, content_hash, PARSER_VERSION, now(), len(pages), json.dumps(quality), spec.model_dump_json())
            self.execute(db, '''INSERT INTO documents VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET title=excluded.title, filed_date=excluded.filed_date,
                source_url=excluded.source_url, acquisition=excluded.acquisition, content_hash=excluded.content_hash,
                parser_version=excluded.parser_version, retrieved_at=excluded.retrieved_at,
                page_count=excluded.page_count, quality=excluded.quality, spec=excluded.spec''', values)
            for page in pages:
                self.execute(db, 'INSERT INTO pages VALUES (?, ?, ?)', (spec.id, page.number, page.text))
            for chunk in chunks:
                self.execute(db, 'INSERT INTO chunks VALUES (?, ?, ?, ?, ?, ?)',
                             (chunk.id, spec.id, chunk.page, chunk.char_start, chunk.char_end, chunk.text))
        return 'updated' if old else 'created'

    def save_extraction(self, document_id, content_hash, model, scope, result):
        with self.connection() as db:
            current = self.execute(db, 'SELECT content_hash FROM documents WHERE id=?', (document_id,)).fetchone()
            if not current or current['content_hash'] != content_hash:
                raise ValueError('Document changed while extraction was running; retry against current content')
            self.execute(db, '''INSERT INTO extractions VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(document_id) DO UPDATE SET content_hash=excluded.content_hash,
                model=excluded.model, created_at=excluded.created_at, scope=excluded.scope, result=excluded.result''',
                (document_id, content_hash, model, now(), json.dumps(scope), result.model_dump_json()))

    def event(self, document_id, status, detail):
        from uuid import uuid4
        with self.connection() as db:
            self.execute(db, 'INSERT INTO ingestion_events VALUES (?, ?, ?, ?, ?)',
                         (str(uuid4()), document_id, now(), status, detail))

    def chunks(self, source=None, case_id=None):
        sql = '''SELECT k.*, d.title, d.source_url, d.content_hash, c.case_name, c.id AS case_id,
                 c.source_system, c.court FROM chunks k JOIN documents d ON k.document_id=d.id
                 JOIN cases c ON d.case_id=c.id WHERE 1=1'''
        args = []
        if source:
            sql += ' AND c.source_system=?'
            args.append(source)
        if case_id:
            sql += ' AND c.id=?'
            args.append(case_id)
        return self.query(sql + ' ORDER BY k.document_id, k.page, k.char_start', args)

    def counts(self):
        return {table: self.query(f'SELECT COUNT(*) AS n FROM {table}')[0]['n']
                for table in ('cases', 'documents', 'pages', 'chunks', 'extractions')}
