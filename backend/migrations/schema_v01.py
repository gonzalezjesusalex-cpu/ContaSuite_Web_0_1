"""Frozen schema for CS-Storage 0002. Do not edit when adding future migrations."""
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import String, Text, ForeignKey, Date, DateTime, JSON, Integer, Boolean, BigInteger, UniqueConstraint, CheckConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
class Base(DeclarativeBase): pass
def uid(): return str(uuid4())
def now(): return datetime.now(timezone.utc)
class Company(Base):
    __tablename__ = 'companies'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    name: Mapped[str] = mapped_column(String(220))
    rfc: Mapped[str] = mapped_column(String(13), unique=True, index=True)
    person_type: Mapped[str] = mapped_column(String(10), default='Moral')
    trade_name: Mapped[str] = mapped_column(String(180), default='')
    regime: Mapped[str] = mapped_column(String(100), default='601 - General de Ley Personas Morales')
    accountant: Mapped[str] = mapped_column(String(150), default='Sin asignar')
    email: Mapped[str] = mapped_column(String(180), default='')
    phone: Mapped[str] = mapped_column(String(40), default='')
    location: Mapped[str] = mapped_column(String(150), default='')
    folder: Mapped[str] = mapped_column(String(1000), default='')
    notes: Mapped[str] = mapped_column(Text, default='')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class Document(Base):
    __tablename__ = 'documents'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    company_id: Mapped[str | None] = mapped_column(ForeignKey('companies.id', ondelete='CASCADE'), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(80), default='General')
    size: Mapped[int] = mapped_column(Integer)
    storage_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    managed: Mapped[bool] = mapped_column(Boolean, default=False, server_default='0')
    storage_revision: Mapped[int] = mapped_column(Integer, default=0, server_default='0')
    document_type: Mapped[str] = mapped_column(String(40), default='unknown', server_default='unknown')
    period: Mapped[str | None] = mapped_column(String(7), nullable=True, index=True)
    classification_status: Mapped[str] = mapped_column(String(20), default='pending', server_default='pending')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class StorageSource(Base):
    __tablename__ = 'storage_sources'
    __table_args__ = (CheckConstraint("kind IN ('local_folder','internal','windows_smb')", name='ck_storage_source_kind'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    label: Mapped[str] = mapped_column(String(160))
    kind: Mapped[str] = mapped_column(String(20))
    root_path: Mapped[str | None] = mapped_column(Text, nullable=True)  # Private; never return ORM objects from an API.
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    configuration: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class DocumentVersion(Base):
    __tablename__ = 'document_versions'
    __table_args__ = (UniqueConstraint('document_id', 'number', name='uq_document_version_number'),
                     CheckConstraint('number > 0 AND size >= 0', name='ck_document_version_numbers'))
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    document_id: Mapped[str] = mapped_column(ForeignKey('documents.id'), index=True)
    number: Mapped[int] = mapped_column(Integer)
    original_name: Mapped[str] = mapped_column(String(255))
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    size: Mapped[int] = mapped_column(BigInteger)
    media_type: Mapped[str] = mapped_column(String(100))
    file_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class DocumentLocation(Base):
    __tablename__ = 'document_locations'
    __table_args__ = (UniqueConstraint('source_id', 'key_digest', 'version_id', name='uq_document_location'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    version_id: Mapped[str] = mapped_column(ForeignKey('document_versions.id'), index=True)
    source_id: Mapped[str] = mapped_column(ForeignKey('storage_sources.id'), index=True)
    relative_key: Mapped[str] = mapped_column(Text)  # Private provider locator.
    key_digest: Mapped[str] = mapped_column(String(64), index=True)
    availability: Mapped[str] = mapped_column(String(20), default='unchecked')
    size: Mapped[int] = mapped_column(BigInteger)
    mtime_ns: Mapped[str | None] = mapped_column(String(30), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(40), nullable=True)

class DocumentCompanyLink(Base):
    __tablename__ = 'document_company_links'
    document_id: Mapped[str] = mapped_column(ForeignKey('documents.id'), primary_key=True)
    company_id: Mapped[str] = mapped_column(ForeignKey('companies.id'), primary_key=True, index=True)
    role: Mapped[str] = mapped_column(String(20), primary_key=True, default='owner')
    method: Mapped[str] = mapped_column(String(20), default='manual')
    confirmed_by: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class StorageIndexJob(Base):
    __tablename__ = 'storage_index_jobs'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    source_id: Mapped[str] = mapped_column(ForeignKey('storage_sources.id'), index=True)
    status: Mapped[str] = mapped_column(String(20), default='queued', index=True)
    requested_by: Mapped[str] = mapped_column(String(100))
    checkpoint: Mapped[dict] = mapped_column(JSON, default=dict)
    counters: Mapped[dict] = mapped_column(JSON, default=dict)
    lease_owner: Mapped[str | None] = mapped_column(String(100), nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class DocumentClassificationReview(Base):
    __tablename__ = 'document_classification_reviews'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    document_id: Mapped[str] = mapped_column(ForeignKey('documents.id'), index=True)
    version_id: Mapped[str] = mapped_column(ForeignKey('document_versions.id'))
    status: Mapped[str] = mapped_column(String(20), default='pending', index=True)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    proposed_links: Mapped[list] = mapped_column(JSON, default=list)
    resolved_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    resolution: Mapped[str | None] = mapped_column(String(40), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class StorageEvent(Base):
    __tablename__ = 'storage_events'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    actor_id: Mapped[str] = mapped_column(String(100))
    action: Mapped[str] = mapped_column(String(60))
    document_id: Mapped[str | None] = mapped_column(ForeignKey('documents.id'), nullable=True, index=True)
    source_id: Mapped[str | None] = mapped_column(ForeignKey('storage_sources.id'), nullable=True)
    company_id: Mapped[str | None] = mapped_column(ForeignKey('companies.id'), nullable=True)
    outcome: Mapped[str] = mapped_column(String(20), default='success')
    code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
