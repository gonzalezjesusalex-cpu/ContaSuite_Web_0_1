"""Renovación del gestor de contraseñas, fase 3: reading the .cer, validating the .key, storing FIEL/CSD and the
internal FIEL service for Declara (no HTTP download of the .cer or the .key)."""

import base64
from types import SimpleNamespace
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives import serialization
from sqlalchemy import select, text

from sat_fixtures import pair
from test_api import client, company  # noqa: F401  Isolated environment before app imports.
from test_accounts import add_user, login, setup
from app import vault_session
from app.credential_crypto import VaultLocked
from app.credential_models import audit, certificates, credentials
from app.database import SessionLocal
from app.models import now
from app.sat_certificates import checks, read_certificate
from app.vault_fiel import FielUnavailable, obtenerFielParaAcceso

RFC = 'SSI260101AB1'
REP = 'HEGT7610034S2'
CURP = 'HEGT761003MDFRNN09'
KEY_PASSWORD = 'Llave-Sintetica-1'
MASTER = 'Maestra-Sintetica-2026!'


def by_id(results):
    return {c['id']: c for c in results}


# ---------------------------------------------------------------- reading and checks


def test_reads_the_sat_fields_of_fiel_and_csd():
    cer, _, _ = pair(representative_rfc=REP, curp=CURP)
    data = read_certificate(cer)
    assert data['holder_name'] == 'SERVICIOS SINTETICOS SA DE CV'
    assert (data['rfc'], data['representative_rfc'], data['curp']) == (RFC, REP, CURP)
    assert data['number'] == '30001000000500003416' and data['detected'] == 'FIEL' and data['issued_by_sat']
    assert data['valid_until'] > data['valid_from'] and len(data['fingerprint']) == 64
    from cryptography import x509

    pem = x509.load_der_x509_certificate(cer).public_bytes(serialization.Encoding.PEM)
    assert read_certificate(pem)['fingerprint'] == data['fingerprint']
    csd = read_certificate(pair(branch='MATRIZ', number='30001000000500009999')[0])
    assert csd['detected'] == 'CSD' and csd['branch'] == 'MATRIZ'


def test_the_six_checks():
    cer, key, _ = pair()
    data, ok = checks(cer, key, KEY_PASSWORD, 'FIEL_EMPRESA', RFC)
    assert all(c['ok'] for c in ok) and data['rfc'] == RFC
    # 1. not a certificate / not issued by the SAT
    assert not by_id(checks(b'no es un cer', key, KEY_PASSWORD, 'FIEL_EMPRESA', RFC)[1])['certificate']['ok']
    other_ca = pair(issuer_org='OTRA AUTORIDAD', seed='otra')[0]
    assert by_id(checks(other_ca, key, KEY_PASSWORD, 'FIEL_EMPRESA', RFC)[1])['certificate']['message'] == (
        'El archivo no es un certificado válido del SAT.'
    )
    # 2. wrong password
    wrong = by_id(checks(cer, key, 'otra-contraseña', 'FIEL_EMPRESA', RFC)[1])
    assert wrong['password']['message'] == 'La contraseña no abre la clave privada.' and not wrong['pair']['ok']
    # 3. a key of another certificate
    _, other_key, _ = pair(number='30001000000500000001', seed='otro-par')
    mismatch = by_id(checks(cer, other_key, KEY_PASSWORD, 'FIEL_EMPRESA', RFC)[1])
    assert mismatch['password']['ok'] and mismatch['pair']['message'] == (
        'La clave privada no corresponde a este certificado.'
    )
    # 4. class detected ≠ chosen: proposes the detected one
    klass = by_id(checks(cer, key, KEY_PASSWORD, 'CSD', RFC)[1])['class']
    assert not klass['ok'] and klass['suggestion'] == 'FIEL_EMPRESA'
    # 5. RFC rules
    assert not by_id(checks(cer, key, KEY_PASSWORD, 'FIEL_EMPRESA', 'OTR010101AB1')[1])['rfc']['ok']
    assert not by_id(checks(cer, key, KEY_PASSWORD, 'FIEL_REPRESENTANTE', RFC)[1])['rfc']['ok']  # 12 characters
    rep_cer, rep_key, _ = pair(rfc=REP, curp=CURP, name='PERSONA SINTETICA', number='30001000000500000002')
    assert by_id(checks(rep_cer, rep_key, KEY_PASSWORD, 'FIEL_REPRESENTANTE', RFC, REP)[1])['rfc']['ok']
    assert not by_id(checks(rep_cer, rep_key, KEY_PASSWORD, 'FIEL_REPRESENTANTE', RFC, 'OTRA7610034S2')[1])['rfc']['ok']
    # 6. expired: not blocking (kept only as history)
    old_cer, old_key, _ = pair(start=-800, end=-1, number='30001000000500000003', seed='vencida')
    validity = by_id(checks(old_cer, old_key, KEY_PASSWORD, 'FIEL_EMPRESA', RFC)[1])['validity']
    assert not validity['ok'] and not validity['blocking']


# ---------------------------------------------------------------- storing through the API


def office(c):
    cid = company(c, name='Servicios Sintéticos', rfc=RFC).json()['id']
    setup(c)
    made = c.post('/api/credentials/vault/setup', json={'password': MASTER, 'confirm': MASTER})
    assert made.status_code == 201
    return cid


def send(c, cid, endpoint, cer, key, password=KEY_PASSWORD, cert_class='FIEL_EMPRESA', **form):
    return c.post(
        f'/api/credentials/companies/{cid}/certificates/{endpoint}',
        files={
            'cer': ('fiel.cer', cer, 'application/octet-stream'),
            'key': ('fiel.key', key, 'application/octet-stream'),
        },
        data={'password': password, 'cert_class': cert_class, **form},
    )


def stored(cid):
    with SessionLocal() as db:
        return list(db.execute(select(certificates).where(certificates.c.company_id == cid)).mappings())


def test_check_then_upload_stores_everything_encrypted(client):  # noqa: F811
    cid = office(client)
    cer, key, _ = pair(representative_rfc=REP, curp=CURP)
    checked = send(client, cid, 'check', cer, key)
    assert checked.status_code == 200, checked.text
    body = checked.json()
    assert all(c['ok'] for c in body['checks']) and body['read']['number'] == '30001000000500003416'
    assert body['sat_access'] == {'cer': 'fiel.cer', 'key': 'fiel.key', 'password': '••••••••', 'rfc': RFC}
    assert KEY_PASSWORD not in checked.text and not stored(cid)  # checking stores nothing
    assert send(client, cid, 'upload', cer, key, password='mala').status_code == 422
    saved = send(client, cid, 'upload', cer, key)
    assert saved.status_code == 201, saved.text
    assert saved.json()['active']
    [row] = stored(cid)
    assert row['cert_class'] == 'FIEL_EMPRESA' and row['active'] and row['holder_rfc'] == RFC
    assert row['holder_curp'] == CURP and row['serial'] == '30001000000500003416'
    with SessionLocal() as db:
        dump = ' '.join(
            str(list(db.execute(text(f'SELECT * FROM {t}'))))
            for t in ('vault_files', 'vault_credentials', 'vault_versions', 'vault_certificates', 'vault_audit')
        )
    for value in (KEY_PASSWORD, base64.b64encode(key).decode()[:40], base64.b64encode(cer).decode()[:40]):
        assert value not in dump
    assert send(client, cid, 'upload', cer, key).status_code == 409  # same certificate twice


def test_replace_history_representative_csd_and_expired(client):  # noqa: F811
    cid = office(client)
    first = pair()
    assert send(client, cid, 'upload', first[0], first[1]).status_code == 201
    renewed = pair(number='30001000000500007777', seed='renovada')
    asked = send(client, cid, 'upload', renewed[0], renewed[1])
    assert asked.status_code == 409 and 'reemplazas' in asked.json()['detail']
    assert send(client, cid, 'check', renewed[0], renewed[1]).json()['replaces'] is True
    assert send(client, cid, 'upload', renewed[0], renewed[1], replace='true').status_code == 201
    rows = {r['serial']: r for r in stored(cid)}
    assert not rows['30001000000500003416']['active'] and rows['30001000000500007777']['active']
    assert rows['30001000000500003416']['replaced_by'] == rows['30001000000500007777']['id']
    rep = pair(rfc=REP, curp=CURP, name='PERSONA SINTETICA', number='30001000000500000002')
    assert send(client, cid, 'upload', rep[0], rep[1], cert_class='FIEL_REPRESENTANTE').status_code == 201
    for branch, number in (('MATRIZ', '30001000000500000010'), ('NORTE', '30001000000500000011')):
        csd = pair(branch=branch, number=number)
        assert send(client, cid, 'upload', csd[0], csd[1], cert_class='CSD').status_code == 201
    old = pair(start=-800, end=-1, number='30001000000500000003', seed='vencida')
    expired = send(client, cid, 'upload', old[0], old[1])
    assert expired.status_code == 201 and expired.json()['active'] is False  # history only, no replace asked
    rows = {r['serial']: r for r in stored(cid)}
    assert rows['30001000000500000002']['cert_class'] == 'FIEL_REPRESENTANTE' and rows['30001000000500000002']['active']
    assert rows['30001000000500000002']['holder_rfc'] == REP and rows['30001000000500000002']['holder_name']
    assert {rows[n]['branch'] for n in ('30001000000500000010', '30001000000500000011')} == {'MATRIZ', 'NORTE'}
    assert rows['30001000000500007777']['active']  # the expired one did not take its place


def test_incomplete_certificate_receives_the_files(client):  # noqa: F811
    cid = office(client)
    ident = client.post(
        f'/api/credentials/companies/{cid}/secrets', json={'service_id': 'fiel_password', 'secret': 'Anterior-1'}
    ).json()['id']
    incomplete = str(uuid4())
    with SessionLocal() as db:
        db.execute(
            certificates.insert().values(
                id=incomplete,
                company_id=cid,
                kind='fiel',
                rfc=RFC,
                holder='company',
                cert_class='FIEL_EMPRESA',
                active=True,
                key_password_id=ident,
                origin='vault',
                reviewed_at=now(),
                notes='Faltan .cer y .key',
                revision=1,
            )
        )
        db.commit()
    cer, key, _ = pair()
    assert send(client, cid, 'upload', cer, key, replace='true').status_code == 201
    [row] = stored(cid)
    assert row['id'] == incomplete and row['fingerprint'] and row['notes'] == '' and row['active']
    shown = client.post(f'/api/credentials/companies/{cid}/secrets/{ident}/reveal').json()['secret']
    assert shown == KEY_PASSWORD  # the password of the key was replaced by the one that opens it


def test_only_administrators_with_the_vault_open(client):  # noqa: F811
    cid = office(client)
    cer, key, _ = pair()
    client.post('/api/credentials/vault/lock')
    assert send(client, cid, 'check', cer, key).status_code == 423
    client.post('/api/credentials/vault/unlock', json={'password': MASTER})
    add_user(client, 'aux', grants=[(cid, 'write')])
    client.cookies.clear()
    login(client, 'aux')
    assert send(client, cid, 'upload', cer, key).status_code == 403


# ---------------------------------------------------------------- Declara and the absence of downloads


def test_internal_service_for_declara_and_no_http_download(client):  # noqa: F811
    cid = office(client)
    cer, key, _ = pair()
    send(client, cid, 'upload', cer, key)
    with SessionLocal() as db:
        session_id = next(iter(vault_session._open))
        admin = db.execute(text('SELECT id FROM user_accounts')).scalar()
    p = SimpleNamespace(
        subject=admin,
        session_id=session_id,
        admin=True,
        bootstrap=False,
        company_ids=frozenset(),
        require_company=lambda *a, **k: None,
    )
    with SessionLocal() as db:
        fiel = obtenerFielParaAcceso(db, p, cid)
    assert (fiel['cer'], fiel['key'], fiel['password'], fiel['rfc']) == (cer, key, KEY_PASSWORD, RFC)
    with SessionLocal() as db:
        assert 'USO_DECLARA' in set(db.scalars(select(audit.c.kind)))
    vault_session.lock(session_id)
    with SessionLocal() as db, pytest.raises(VaultLocked):
        obtenerFielParaAcceso(db, p, cid)
    other = company(client, name='Sin FIEL', rfc='SFI260101AB1').json()['id']
    vault_session.unlock(session_id, admin, 'x', b'\0' * 32, 5)
    with SessionLocal() as db, pytest.raises(FielUnavailable):
        obtenerFielParaAcceso(db, p, other)
    # No route hands out the .cer or the .key.
    client.post('/api/credentials/vault/lock')
    client.post('/api/credentials/vault/unlock', json={'password': MASTER})
    with SessionLocal() as db:
        fiel_id = db.execute(select(credentials.c.id).where(credentials.c.kind == 'LLAVE')).scalar()
    ticket = client.post(f'/api/credentials/companies/{cid}/secrets/{fiel_id}/ticket', json={'purpose': 'sat_fiel'})
    assert ticket.status_code == 422
    files_post = client.post(
        f'/api/credentials/companies/{cid}/secrets/{fiel_id}/files',
        files={'file': ('a.key', key, 'application/octet-stream')},
    )
    assert files_post.status_code == 410
    encoded = (base64.b64encode(cer).decode()[:40], base64.b64encode(key).decode()[:40])
    for path in (
        '/api/credentials/vault',
        f'/api/credentials/companies/{cid}',
        f'/api/credentials/companies/{cid}/history',
        '/api/credentials/vault/state',
    ):
        body = client.get(path).text
        assert not any(e in body for e in encoded), path
    from app.main import app

    paths = {getattr(r, 'path', '') for r in app.routes}
    assert not any('download' in x and '/credentials' in x for x in paths)
