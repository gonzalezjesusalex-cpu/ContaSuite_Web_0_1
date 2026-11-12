from dataclasses import dataclass
from datetime import datetime
from typing import BinaryIO
from pydantic import BaseModel, ConfigDict


class SourcePublic(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str
    label: str
    kind: str
    enabled: bool
    state: str
    code: str | None = None


class DocumentPublic(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str
    name: str
    size: int
    revision: int
    company_ids: list[str]
    document_type: str
    period: str | None
    classification_status: str
    created_at: datetime


class CompanyPublic(BaseModel):
    id: str
    name: str
    rfc: str


class LocationPublic(BaseModel):
    source_id: str
    label: str
    kind: str
    availability: str
    last_seen_at: datetime | None = None
    error_code: str | None = None


class CatalogDocument(DocumentPublic):
    category: str
    format: str
    companies: list[CompanyPublic]
    sources: list[LocationPublic]
    availability: str


class CatalogPage(BaseModel):
    items: list[CatalogDocument]
    total: int
    pending_count: int
    offset: int
    limit: int


class VersionPublic(BaseModel):
    number: int
    original_name: str
    sha256: str | None
    size: int
    media_type: str
    created_at: datetime


class DocumentDetail(BaseModel):
    document: CatalogDocument
    versions: list[VersionPublic]


@dataclass
class VerifiedContent:
    document: DocumentPublic
    media_type: str
    stream: BinaryIO
    filename: str | None = None
