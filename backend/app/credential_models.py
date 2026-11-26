"""Separate metadata: these tables are never created by application startup."""

from sqlalchemy import MetaData, Table, Column, String, Integer, Boolean, JSON, DateTime, ForeignKey, UniqueConstraint
from .models import Company, UserAccount, Document

metadata = MetaData()
services = Table(
    'vault_services', metadata, Column('id', String(50), primary_key=True), Column('label', String(100), nullable=False)
)
grants = Table(
    'vault_grants',
    metadata,
    Column('user_id', ForeignKey(UserAccount.id), primary_key=True),
    Column('company_id', ForeignKey(Company.id), primary_key=True),
    Column('permission', String(30), primary_key=True),
)
credentials = Table(
    'vault_credentials',
    metadata,
    Column('id', String(36), primary_key=True),
    Column('company_id', ForeignKey(Company.id), nullable=False),
    Column('service_id', ForeignKey(services.c.id), nullable=False),
    Column('label', String(100), nullable=False),
    Column('envelope', JSON, nullable=False),
    Column('revision', Integer, nullable=False),
    Column('archived', Boolean, nullable=False),
    Column('created_at', DateTime(timezone=True), nullable=False),
    Column('updated_at', DateTime(timezone=True), nullable=False),
    # cs_0021, plan v1.1 Cambio 4 (password manager): visible user, portal address, notes (never secrets),
    # extra data (registro patronal…), whose FIEL/CSD it is, local strength (0-4) and a keyed fingerprint to find
    # repeated passwords without decrypting them.
    Column('username', String(200)),
    Column('url', String(500)),
    Column('notes', String(2000)),
    Column('extra', JSON),
    Column('holder', String(12)),
    Column('strength', Integer),
    Column('fingerprint', String(64)),
)
versions = Table(
    'vault_versions',
    metadata,
    Column('credential_id', ForeignKey(credentials.c.id), primary_key=True),
    Column('revision', Integer, primary_key=True),
    Column('envelope', JSON, nullable=False),
    Column('actor_id', String(100), nullable=False),
    Column('created_at', DateTime(timezone=True), nullable=False),
)
certificates = Table(
    'vault_certificates',
    metadata,
    Column('id', String(36), primary_key=True),
    Column('company_id', ForeignKey(Company.id), nullable=False),
    Column('document_id', ForeignKey(Document.id)),
    Column('kind', String(10), nullable=False),
    Column('rfc', String(13), nullable=False),
    Column('serial', String(100)),
    Column('subject', String(1000)),
    Column('fingerprint', String(64)),
    Column('valid_from', DateTime(timezone=True)),
    Column('valid_until', DateTime(timezone=True)),
    Column('origin', String(30), nullable=False),
    Column('reviewed_at', DateTime(timezone=True), nullable=False),
    Column('notes', String(2000), nullable=False),
    Column('revision', Integer, nullable=False),
    # cs_0021: whose certificate it is: the company or its legal representative (a second FIEL).
    Column('holder', String(12)),
    UniqueConstraint('company_id', 'fingerprint', 'kind'),
)
# cs_0021: encrypted FIEL/CSD/IMSS files (.cer, .key) of a credential, outside the document folders. Never indexed
# by CS-Storage nor read by the agent; never downloaded: used only through the browser extension's one-time ticket.
files = Table(
    'vault_files',
    metadata,
    Column('id', String(36), primary_key=True),
    Column('company_id', ForeignKey(Company.id), nullable=False),
    Column('credential_id', ForeignKey(credentials.c.id), nullable=False),
    Column('file_kind', String(10), nullable=False),
    Column('file_name', String(255), nullable=False),
    Column('envelope', JSON, nullable=False),
    Column('sha256', String(64), nullable=False),
    Column('size', Integer, nullable=False),
    Column('certificate_id', String(36)),
    Column('actor_id', String(100), nullable=False),
    Column('created_at', DateTime(timezone=True), nullable=False),
)
# cs_0021: one-time tickets for the browser extension (60 s, single use); only the hash is stored.
tickets = Table(
    'vault_tickets',
    metadata,
    Column('token_hash', String(64), primary_key=True),
    Column('credential_id', ForeignKey(credentials.c.id), nullable=False),
    Column('company_id', ForeignKey(Company.id), nullable=False),
    Column('actor_id', String(100), nullable=False),
    Column('purpose', String(20), nullable=False),
    Column('expires_at', DateTime(timezone=True), nullable=False),
    Column('used_at', DateTime(timezone=True)),
)
audit = Table(
    'vault_audit',
    metadata,
    Column('id', String(36), primary_key=True),
    Column('company_id', ForeignKey(Company.id)),
    Column('actor_id', String(100), nullable=False),
    Column('action', String(40), nullable=False),
    Column('record_id', String(100)),
    Column('created_at', DateTime(timezone=True), nullable=False),
    Column('metadata', JSON, nullable=False),
)
# cs_0022, renovación del gestor: one row per installation. Never stores the master password nor the data key.
vault_config = Table(
    'vault_config',
    metadata,
    Column('id', Integer, primary_key=True),
    Column('data_key_id', String(36), nullable=False),
    Column('auto_lock_minutes', Integer, nullable=False),
    Column('created_at', DateTime(timezone=True), nullable=False),
    Column('created_by', String(100), nullable=False),
    # How many sealed envelopes of the previous DPAPI keyring were re-wrapped when the vault was created.
    Column('migrated', JSON, nullable=False),
)
# cs_0022: one wrapped copy of the data key per authorized person, plus the recovery code's copy. `kind` is
# 'user' (own master password), 'invite' (temporary code given by the administrator; must be changed) or
# 'recovery'. Failed attempts and the wait after five failures are kept on the person's own row.
vault_keys = Table(
    'vault_keys',
    metadata,
    Column('id', String(36), primary_key=True),
    Column('kind', String(10), nullable=False),
    Column('user_id', ForeignKey(UserAccount.id)),
    Column('salt', String(64), nullable=False),
    Column('kdf', JSON, nullable=False),
    Column('wrapped_key', String(200), nullable=False),
    Column('nonce', String(32), nullable=False),
    Column('failed_attempts', Integer, nullable=False),
    Column('blocked_until', DateTime(timezone=True)),
    Column('created_at', DateTime(timezone=True), nullable=False),
    Column('created_by', String(100), nullable=False),
    UniqueConstraint('kind', 'user_id'),
)
settings = Table(
    'vault_alert_settings',
    metadata,
    Column('id', Integer, primary_key=True),
    Column('thresholds', JSON, nullable=False),
)
alerts = Table(
    'vault_alerts',
    metadata,
    Column('id', String(64), primary_key=True),
    Column('company_id', ForeignKey(Company.id), nullable=False),
    Column('source', String(30), nullable=False),
    Column('reference', String(100), nullable=False),
    Column('kind', String(40), nullable=False),
    Column('priority', String(10), nullable=False),
    Column('generated_at', DateTime(timezone=True), nullable=False),
    Column('due_at', DateTime(timezone=True)),
    Column('state', String(12), nullable=False),
    UniqueConstraint('source', 'reference', 'kind'),
)
INITIAL = {
    'sat_password': 'Contraseña SAT',
    'fiel_password': 'Contraseña e.firma',
    'csd_password': 'Contraseña sello digital',
    'imss_registration': 'Registro patronal',
    'idse_user': 'Usuario IDSE',
    'idse_password': 'Contraseña IDSE',
    'sipare_user': 'Usuario SIPARE',
    'sipare_password': 'Contraseña SIPARE',
    'infonavit_user': 'Usuario INFONAVIT',
    'infonavit_password': 'Contraseña INFONAVIT',
    'payroll_tax': 'Impuesto sobre nómina',
    'email': 'Correo electrónico',
    'fel': 'FEL Facturación',
    'contpaqi_payroll': 'CONTPAQi Nóminas',
    'external_billing': 'Facturación externa',
    'other': 'Otros servicios',
}
# cs_0021: portals of the password manager (one credential = portal + user + password).
PORTALS = {
    'fiel': 'FIEL (e.firma)',
    'csd': 'CSD (sello digital)',
    'idse': 'IMSS – IDSE',
    'sipare': 'IMSS – SIPARE',
    'imss_certificate': 'IMSS – certificado digital',
    'infonavit': 'Infonavit – portal empresarial',
    'state_isn': 'Portal estatal (ISN)',
    'bank': 'Banco',
}
