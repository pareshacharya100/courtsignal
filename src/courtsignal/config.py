from dataclasses import dataclass, field
from pathlib import Path
import os


def load_env(path: Path = Path('.env')) -> None:
    """Load plain KEY=VALUE configuration without executing shell expressions."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"\''))


@dataclass(frozen=True)
class Settings:
    database_url: str = 'sqlite:///data/courtsignal.db'
    data_dir: Path = Path('data')
    anthropic_key: str = field(default='', repr=False)
    anthropic_model: str = 'claude-sonnet-4-6'
    voyage_key: str = field(default='', repr=False)
    voyage_model: str = 'voyage-4-lite'
    embedding_dimension: int = 1024
    pinecone_key: str = field(default='', repr=False)
    pinecone_host: str = ''
    pinecone_namespace: str = 'courtsignal-dev'
    courtlistener_token: str = field(default='', repr=False)

    @classmethod
    def from_env(cls):
        load_env()
        return cls(
            database_url=os.getenv('DATABASE_URL', cls.database_url),
            data_dir=Path(os.getenv('DATA_DIR', 'data')),
            anthropic_key=os.getenv('ANTHROPIC_API_KEY', ''),
            anthropic_model=os.getenv('ANTHROPIC_MODEL', cls.anthropic_model),
            voyage_key=os.getenv('VOYAGE_API_KEY', ''),
            voyage_model=os.getenv('VOYAGE_MODEL', cls.voyage_model),
            embedding_dimension=int(os.getenv('EMBEDDING_DIMENSION', '1024')),
            pinecone_key=os.getenv('PINECONE_API_KEY', ''),
            pinecone_host=os.getenv('PINECONE_INDEX_HOST', ''),
            pinecone_namespace=os.getenv('PINECONE_NAMESPACE', cls.pinecone_namespace),
            courtlistener_token=os.getenv('COURTLISTENER_TOKEN', ''),
        )

    @property
    def semantic_ready(self):
        return bool(self.voyage_key and self.pinecone_key and self.pinecone_host)
