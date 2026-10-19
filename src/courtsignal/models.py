"""Canonical contracts keep acquisition metadata separate from inferred facts."""
from datetime import date
from hashlib import sha256
from typing import Literal
from urllib.parse import urlparse
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def stable_id(*parts: str) -> str:
    return sha256('\x1f'.join(parts).encode()).hexdigest()


class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Case(Contract):
    source_system: Literal['pacer', 'nyscef']
    court: str = Field(min_length=1)
    docket_number: str = Field(min_length=1)
    case_name: str = Field(min_length=1)

    @property
    def id(self):
        # Court is part of the identity: index numbers are not globally unique.
        return stable_id(self.source_system, self.court.lower(), self.docket_number.strip().lower())


class DocumentSpec(Contract):
    case: Case
    document_number: str = Field(min_length=1)
    attachment_number: str = '0'
    title: str = Field(min_length=1)
    filed_date: date | None = None
    download_url: str
    acquisition: Literal['published_mirror', 'nyscef_public_document', 'recap_api']
    expected_sha256: str | None = None
    # Project-archived copy of the same bytes, used only when the original source refuses access.
    fallback_url: str | None = None

    @field_validator('download_url', 'fallback_url')
    @classmethod
    def public_https(cls, value):
        if value is None:
            return value
        parsed = urlparse(value)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError('Document sources must be HTTPS URLs without embedded credentials')
        return value

    @model_validator(mode='after')
    def fallback_requires_pin(self):
        if self.fallback_url and not self.expected_sha256:
            raise ValueError('A fallback copy is trusted only with a pinned expected_sha256')
        return self

    @property
    def id(self):
        return stable_id(self.case.id, self.document_number, self.attachment_number)


class Page(Contract):
    number: int = Field(ge=1)
    text: str


class Chunk(Contract):
    id: str
    document_id: str
    page: int = Field(ge=1)
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=1)
    text: str = Field(min_length=1)


class Fact(Contract):
    field: Literal['document_type', 'judge', 'filing_date', 'motion_type', 'disposition']
    value: str = Field(min_length=1, max_length=500)
    page: int = Field(ge=1)
    quote: str = Field(min_length=8, max_length=1500)


class Extraction(Contract):
    facts: list[Fact] = Field(default_factory=list, max_length=20)


class Claim(Contract):
    text: str = Field(min_length=1, max_length=1000)
    chunk_id: str
    quote: str = Field(min_length=8, max_length=1500)


class Answer(Contract):
    claims: list[Claim] = Field(default_factory=list, max_length=6)
    abstained: bool = False
