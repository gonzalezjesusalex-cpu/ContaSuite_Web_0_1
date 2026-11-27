"""Renovación del gestor de contraseñas, fase 2: credential types, certificate classes and the access log.

Additive and idempotent. No secret is created, read or decrypted (envelopes stay where they are: the key password of
a FIEL/CSD keeps living in its encrypted credential, which the certificate now references).

- vault_credentials: `kind` (SAT_CIEC, IMSS_IDSE, SIPARE, INFONAVIT, CORREO, OTRO, or LLAVE for the password of a
  private key), `requires_review`, `updated_by`. Filled from the existing portal of each credential.
- vault_certificates: `cert_class` (FIEL_EMPRESA, FIEL_REPRESENTANTE, CSD), holder name/RFC/CURP, `branch`,
  `active`, `replaced_by` and `key_password_id`. Only one active FIEL of each class per company: the one that ends
  last stays active, the others go to the history. A FIEL/CSD password without certificate gets an incomplete
  certificate («Faltan .cer y .key»).
- vault_audit: `kind` (action of the spec), `resource_type` and `client` (address of the computer). Old rows get the
  same translation; no row is deleted.

Apply only through scripts/schema_admin.py with a backup.
"""

from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision = 'cs_0024_vault_types_classes'
down_revision = 'cs_0023_declara_v2'
branch_labels = None
depends_on = None

KINDS = {
    'sat_password': 'SAT_CIEC',
    'idse': 'IMSS_IDSE',
    'idse_user': 'IMSS_IDSE',
    'idse_password': 'IMSS_IDSE',
    'imss_certificate': 'IMSS_IDSE',
    'sipare': 'SIPARE',
    'sipare_user': 'SIPARE',
    'sipare_password': 'SIPARE',
    'infonavit': 'INFONAVIT',
    'infonavit_user': 'INFONAVIT',
    'infonavit_password': 'INFONAVIT',
    'email': 'CORREO',
    'fiel': 'LLAVE',
    'csd': 'LLAVE',
    'fiel_password': 'LLAVE',
    'csd_password': 'LLAVE',
}
ACTIONS = {
    'vault_unlocked': ('DESBLOQUEAR', 'boveda'),
    'vault_unlock_failed': ('DESBLOQUEO_FALLIDO', 'boveda'),
    'secret_revealed': ('VER', 'credencial'),
    'secret_copied': ('COPIAR', 'credencial'),
    'credential_created': ('CREAR', 'credencial'),
    'credential_modified': ('EDITAR', 'credencial'),
    'credential_archived': ('ELIMINAR', 'credencial'),
    'certificate_created': ('CREAR', 'certificado'),
    'certificate_modified': ('EDITAR', 'certificado'),
    'vault_file_stored': ('EDITAR', 'certificado'),
    'vault_file_removed': ('EDITAR', 'certificado'),
    'vault_imported': ('IMPORTAR', 'importacion'),
    'vault_exported': ('EXPORTAR', 'exportacion'),
    'autofill_used': ('USO_DECLARA', 'credencial'),
}


def add(inspector, table, columns):
    existing = {c['name'] for c in inspector.get_columns(table)}
    for name, kind in columns:
        if name not in existing:
            op.add_column(table, sa.Column(name, kind, nullable=True))


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table('vault_credentials'):
        return
    add(
        inspector,
        'vault_credentials',
        [('kind', sa.String(12)), ('requires_review', sa.Boolean()), ('updated_by', sa.String(100))],
    )
    add(
        inspector,
        'vault_certificates',
        [
            ('cert_class', sa.String(20)),
            ('holder_name', sa.String(300)),
            ('holder_rfc', sa.String(13)),
            ('holder_curp', sa.String(18)),
            ('branch', sa.String(200)),
            ('active', sa.Boolean()),
            ('replaced_by', sa.String(36)),
            ('key_password_id', sa.String(36)),
        ],
    )
    add(
        inspector,
        'vault_audit',
        [('kind', sa.String(20)), ('resource_type', sa.String(20)), ('client', sa.String(100))],
    )

    creds = sa.table(
        'vault_credentials',
        sa.column('id', sa.String),
        sa.column('company_id', sa.String),
        sa.column('service_id', sa.String),
        sa.column('holder', sa.String),
        sa.column('archived', sa.Boolean),
        sa.column('kind', sa.String),
        sa.column('requires_review', sa.Boolean),
    )
    certs = sa.table(
        'vault_certificates',
        sa.column('id', sa.String),
        sa.column('company_id', sa.String),
        sa.column('kind', sa.String),
        sa.column('rfc', sa.String),
        sa.column('holder', sa.String),
        sa.column('valid_until', sa.DateTime(timezone=True)),
        sa.column('cert_class', sa.String),
        sa.column('holder_rfc', sa.String),
        sa.column('active', sa.Boolean),
        sa.column('replaced_by', sa.String),
        sa.column('key_password_id', sa.String),
        sa.column('origin', sa.String),
        sa.column('reviewed_at', sa.DateTime(timezone=True)),
        sa.column('notes', sa.String),
        sa.column('revision', sa.Integer),
    )
    files = sa.table('vault_files', sa.column('credential_id', sa.String), sa.column('certificate_id', sa.String))
    audit = sa.table(
        'vault_audit',
        sa.column('action', sa.String),
        sa.column('kind', sa.String),
        sa.column('resource_type', sa.String),
    )

    for row in bind.execute(sa.select(creds.c.id, creds.c.service_id).where(creds.c.kind.is_(None))):
        bind.execute(
            creds.update()
            .where(creds.c.id == row.id)
            .values(kind=KINDS.get(row.service_id, 'OTRO'), requires_review=False)
        )

    def cert_class(kind, holder):
        if kind == 'csd':
            return 'CSD'
        if kind == 'fiel':
            return 'FIEL_REPRESENTANTE' if holder == 'legal_rep' else 'FIEL_EMPRESA'
        return None

    for row in bind.execute(
        sa.select(certs.c.id, certs.c.kind, certs.c.holder, certs.c.rfc).where(certs.c.cert_class.is_(None))
    ):
        klass = cert_class(row.kind, row.holder)
        bind.execute(
            certs.update()
            .where(certs.c.id == row.id)
            .values(cert_class=klass, active=True, holder_rfc=row.rfc if klass in ('FIEL_EMPRESA', 'CSD') else None)
        )
    # Key password of each certificate: the credential whose encrypted files belong to it.
    for credential_id, certificate_id in bind.execute(
        sa.select(files.c.credential_id, files.c.certificate_id).where(files.c.certificate_id.is_not(None))
    ):
        bind.execute(
            certs.update()
            .where(certs.c.id == certificate_id, certs.c.key_password_id.is_(None))
            .values(key_password_id=credential_id)
        )
    # A FIEL/CSD password without certificate: an incomplete certificate («Faltan .cer y .key»).
    linked = {
        r[0] for r in bind.execute(sa.select(certs.c.key_password_id).where(certs.c.key_password_id.is_not(None)))
    }
    rfcs = dict(bind.execute(sa.text('SELECT id, rfc FROM companies')).all())
    for row in bind.execute(
        sa.select(creds.c.id, creds.c.company_id, creds.c.service_id, creds.c.holder).where(
            creds.c.kind == 'LLAVE', creds.c.archived.is_(False)
        )
    ):
        if row.id in linked:
            continue
        kind = 'csd' if row.service_id.startswith('csd') else 'fiel'
        klass = cert_class(kind, row.holder)
        bind.execute(
            certs.insert().values(
                id=str(uuid4()),
                company_id=row.company_id,
                kind=kind,
                rfc=rfcs.get(row.company_id, ''),
                holder=row.holder or 'company',
                cert_class=klass,
                holder_rfc=rfcs.get(row.company_id) if klass != 'FIEL_REPRESENTANTE' else None,
                active=True,
                key_password_id=row.id,
                origin='vault',
                reviewed_at=sa.func.now(),
                notes='Faltan .cer y .key',
                revision=1,
            )
        )
    # One active FIEL of each class per company: the one that ends last; the others go to the history.
    rows = list(
        bind.execute(
            sa.select(certs.c.id, certs.c.company_id, certs.c.cert_class, certs.c.valid_until).where(
                certs.c.cert_class.in_(('FIEL_EMPRESA', 'FIEL_REPRESENTANTE')), certs.c.active.is_(True)
            )
        )
    )
    groups = {}
    for r in rows:
        groups.setdefault((r.company_id, r.cert_class), []).append(r)
    for group in groups.values():
        if len(group) < 2:
            continue
        group.sort(key=lambda r: (r.valid_until is not None, r.valid_until or 0), reverse=True)
        winner = group[0].id
        for loser in group[1:]:
            bind.execute(certs.update().where(certs.c.id == loser.id).values(active=False, replaced_by=winner))

    for action, (kind, resource) in ACTIONS.items():
        bind.execute(
            audit.update()
            .where(audit.c.action == action, audit.c.kind.is_(None))
            .values(kind=kind, resource_type=resource)
        )


def downgrade():
    raise RuntimeError('Las columnas del gestor guardan la historia de los certificados; sin reversión.')
