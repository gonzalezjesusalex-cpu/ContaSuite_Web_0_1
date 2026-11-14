from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import (
    String,
    Text,
    ForeignKey,
    Date,
    DateTime,
    JSON,
    Integer,
    Boolean,
    BigInteger,
    UniqueConstraint,
    CheckConstraint,
    event,
    inspect,
)
from sqlalchemy.orm import Mapped, mapped_column, validates
from .database import Base


def uid():
    return str(uuid4())


def now():
    return datetime.now(timezone.utc)


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
    # cs_0011: the responsible accountant by user id (no FK: added to existing tables; checked in
    # app/responsible.py). `accountant` above becomes the shown name; `accountant_legacy` keeps the original
    # free text until an administrator confirms its retirement.
    accountant_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    accountant_legacy: Mapped[str | None] = mapped_column(String(150), nullable=True)
    # cs_0012, Bloque 1: data of the Constancia de Situación Fiscal (all optional; the form asks for them).
    idcif: Mapped[str | None] = mapped_column(String(11), nullable=True)
    curp: Mapped[str | None] = mapped_column(String(18), nullable=True)
    tax_postal_code: Mapped[str | None] = mapped_column(String(5), nullable=True)
    tax_street_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    tax_street: Mapped[str | None] = mapped_column(String(200), nullable=True)
    tax_exterior_number: Mapped[str | None] = mapped_column(String(40), nullable=True)
    tax_interior_number: Mapped[str | None] = mapped_column(String(40), nullable=True)
    tax_neighborhood: Mapped[str | None] = mapped_column(String(200), nullable=True)
    tax_locality: Mapped[str | None] = mapped_column(String(200), nullable=True)
    tax_municipality: Mapped[str | None] = mapped_column(String(200), nullable=True)
    tax_state: Mapped[str | None] = mapped_column(String(80), nullable=True)
    tax_between_streets: Mapped[str | None] = mapped_column(String(300), nullable=True)
    operations_start: Mapped[__import__('datetime').date | None] = mapped_column(Date, nullable=True)
    padron_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    csf_issued_on: Mapped[__import__('datetime').date | None] = mapped_column(Date, nullable=True)
    email: Mapped[str] = mapped_column(String(180), default='')
    phone: Mapped[str] = mapped_column(String(40), default='')
    location: Mapped[str] = mapped_column(String(150), default='')
    folder: Mapped[str] = mapped_column(String(1000), default='')
    notes: Mapped[str] = mapped_column(Text, default='')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class CompanyRegime(Base):
    """Every current tax regime of a company, the main one first (cs_0012, Bloque 1)."""

    __tablename__ = 'company_regimes'
    company_id: Mapped[str] = mapped_column(ForeignKey('companies.id', ondelete='CASCADE'), primary_key=True)
    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str | None] = mapped_column(String(3), nullable=True)
    label: Mapped[str] = mapped_column(String(250))
    start_date: Mapped[__import__('datetime').date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[__import__('datetime').date | None] = mapped_column(Date, nullable=True)


class Task(Base):
    __tablename__ = 'tasks'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    company_id: Mapped[str] = mapped_column(ForeignKey('companies.id', ondelete='CASCADE'), index=True)
    title: Mapped[str] = mapped_column(String(250))
    category: Mapped[str] = mapped_column(String(80), default='Operativa')
    responsible: Mapped[str] = mapped_column(String(150), default='Sin asignar')
    due_date: Mapped[__import__('datetime').date] = mapped_column(Date)
    priority: Mapped[str] = mapped_column(String(20), default='Media')
    status: Mapped[str] = mapped_column(String(30), default='Pendiente')
    notes: Mapped[str] = mapped_column(Text, default='')


class Obligation(Base):
    __tablename__ = 'obligations'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    company_id: Mapped[str] = mapped_column(ForeignKey('companies.id', ondelete='CASCADE'), index=True)
    title: Mapped[str] = mapped_column(String(180))
    period: Mapped[str] = mapped_column(String(7), index=True)
    due_date: Mapped[__import__('datetime').date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(30), default='Pendiente')
    reference: Mapped[str] = mapped_column(String(180), default='')
    notes: Mapped[str] = mapped_column(Text, default='')


class Document(Base):
    __tablename__ = 'documents'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    company_id: Mapped[str | None] = mapped_column(
        ForeignKey('companies.id', ondelete='CASCADE'), nullable=True, index=True
    )
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


class Audit(Base):
    __tablename__ = 'audit_events'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    company_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(250))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    # cs_0010: who made the change (user id; NULL for system work or rows before roles) and, for edits,
    # {field: {'before': old, 'after': new}}.
    actor_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    changes: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class Agent(Base):
    __tablename__ = 'agents'
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    capabilities: Mapped[list] = mapped_column(JSON, default=list)


class Job(Base):
    __tablename__ = 'jobs'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    company_id: Mapped[str] = mapped_column(ForeignKey('companies.id', ondelete='CASCADE'), index=True)
    agent_id: Mapped[str] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(String(60))
    status: Mapped[str] = mapped_column(String(30), default='queued')
    payload: Mapped[dict] = mapped_column(JSON)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(String(200))


class Receipt(Base):
    __tablename__ = 'receipts'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    company_id: Mapped[str | None] = mapped_column(ForeignKey('companies.id'), nullable=True, index=True)
    client_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    concept: Mapped[str] = mapped_column(String(1000), default='', server_default='')
    folio: Mapped[str] = mapped_column(String(30), unique=True)
    name: Mapped[str] = mapped_column(String(220))
    month: Mapped[int] = mapped_column(Integer)
    year: Mapped[int] = mapped_column(Integer)
    amount: Mapped[str] = mapped_column(String(30))
    issued: Mapped[str] = mapped_column(String(10))
    receiver: Mapped[str] = mapped_column(String(180))
    place: Mapped[str] = mapped_column(String(180))
    filename: Mapped[str] = mapped_column(String(255))
    storage_name: Mapped[str] = mapped_column(String(100))
    created_by: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)  # cs_0009
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ReceiptCounter(Base):
    __tablename__ = 'receipt_counters'
    year: Mapped[int] = mapped_column(Integer, primary_key=True)
    seq: Mapped[int] = mapped_column(Integer)


class ReceiptClient(Base):
    __tablename__ = 'receipt_clients'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(220))
    normalized_name: Mapped[str] = mapped_column(String(220), unique=True)


class RecopilaRun(Base):
    __tablename__ = 'recopila_runs'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    company_id: Mapped[str | None] = mapped_column(ForeignKey('companies.id'), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(30), default='analyzing')
    message: Mapped[str] = mapped_column(String(1000), default='')
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    by_month: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)  # cs_0009
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class OrganizadorRun(Base):
    __tablename__ = 'organizador_runs'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    company_id: Mapped[str | None] = mapped_column(ForeignKey('companies.id'), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(30), default='analyzing')
    message: Mapped[str] = mapped_column(String(1000), default='')
    options: Mapped[dict] = mapped_column(JSON, default=dict)
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    created_by: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)  # cs_0009
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class DeclaraRun(Base):
    __tablename__ = 'declara_runs'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    company_id: Mapped[str] = mapped_column(ForeignKey('companies.id'), index=True)
    short_name: Mapped[str] = mapped_column(String(100))
    expected_rfc: Mapped[str] = mapped_column(String(13))
    name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(30), default='analyzing')
    revision: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str] = mapped_column(String(1000), default='')
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    months: Mapped[dict] = mapped_column(JSON, default=dict)
    evaluated_on: Mapped[str] = mapped_column(String(10), default='')
    created_by: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)  # cs_0009
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class StorageSource(Base):
    __tablename__ = 'storage_sources'
    __table_args__ = (
        CheckConstraint("kind IN ('local_folder','internal','windows_smb')", name='ck_storage_source_kind'),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    label: Mapped[str] = mapped_column(String(160))
    kind: Mapped[str] = mapped_column(String(20))
    root_path: Mapped[str | None] = mapped_column(Text, nullable=True)  # Private; never return ORM objects from an API.
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    configuration: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default='1')
    interval_minutes: Mapped[int] = mapped_column(Integer, default=0, server_default='0')
    next_scan_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    check_state: Mapped[str] = mapped_column(String(30), default='unchecked', server_default='unchecked')
    check_code: Mapped[str | None] = mapped_column(String(40), nullable=True)


class StorageWorkerState(Base):
    __tablename__ = 'storage_worker_state'
    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    owner: Mapped[str] = mapped_column(String(100))
    heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DocumentVersion(Base):
    __tablename__ = 'document_versions'
    __table_args__ = (
        UniqueConstraint('document_id', 'number', name='uq_document_version_number'),
        CheckConstraint('number > 0 AND size >= 0', name='ck_document_version_numbers'),
    )
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
    status: Mapped[str] = mapped_column(String(32), default='queued', index=True)
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


class IdentityState(Base):
    __tablename__ = 'identity_state'
    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    initialized: Mapped[bool] = mapped_column(Boolean, default=False)


ROLES = ('admin', 'contador', 'auxiliar')


class UserAccount(Base):
    __tablename__ = 'user_accounts'
    __table_args__ = (CheckConstraint("role IN ('admin', 'contador', 'auxiliar')", name='ck_user_account_role'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    display_name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(String(255))
    # `role` is the source of truth (migration cs_0007). `admin` stays in step for code and scripts that still
    # read or assign the boolean; the validators below keep both columns consistent whichever one is set.
    role: Mapped[str] = mapped_column(String(20), server_default='auxiliar')
    admin: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    @validates('role')
    def _valid_role(self, _key, value):
        if value not in ROLES:
            raise ValueError('Rol de usuario no válido.')
        return value


@event.listens_for(UserAccount, 'before_insert')
def _role_on_insert(_mapper, _connection, user):
    # An explicit role wins; otherwise the legacy boolean decides (admin, or the least privileged role).
    if user.role is None:
        user.role = 'admin' if user.admin else 'auxiliar'
    user.admin = user.role == 'admin'


@event.listens_for(UserAccount, 'before_update')
def _role_on_update(_mapper, _connection, user):
    if inspect(user).attrs.role.history.has_changes():
        user.admin = user.role == 'admin'
    elif inspect(user).attrs.admin.history.has_changes():
        user.role = 'admin' if user.admin else ('auxiliar' if user.role == 'admin' else user.role)


class UserCompanyGrant(Base):
    __tablename__ = 'user_company_grants'
    __table_args__ = (CheckConstraint("access IN ('read', 'write')", name='ck_user_company_access'),)
    user_id: Mapped[str] = mapped_column(ForeignKey('user_accounts.id'), primary_key=True)
    company_id: Mapped[str] = mapped_column(ForeignKey('companies.id'), primary_key=True)
    access: Mapped[str] = mapped_column(String(10))


class UserCompanyAction(Base):
    """Explicit actions of an auxiliar in one company (catalog in app/permissions.py; migration cs_0008)."""

    __tablename__ = 'user_company_actions'
    user_id: Mapped[str] = mapped_column(ForeignKey('user_accounts.id'), primary_key=True)
    company_id: Mapped[str] = mapped_column(ForeignKey('companies.id'), primary_key=True)
    action: Mapped[str] = mapped_column(String(40), primary_key=True)


class UserSession(Base):
    __tablename__ = 'user_sessions'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('user_accounts.id'), index=True)
    csrf_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LoginThrottle(Base):
    __tablename__ = 'login_throttles'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    window_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class SecurityEvent(Base):
    __tablename__ = 'security_events'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    actor_id: Mapped[str] = mapped_column(String(100))
    action: Mapped[str] = mapped_column(String(160))
    outcome: Mapped[str] = mapped_column(String(20))
    code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
