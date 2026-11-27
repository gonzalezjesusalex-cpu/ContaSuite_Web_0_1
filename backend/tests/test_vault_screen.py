"""Renovación del gestor de contraseñas, fase 5: what the main screen needs (certificates, FIEL badge per company,
the four indicators of «Revisión de seguridad») and «Eliminar» a certificate."""

from sat_fixtures import pair
from test_api import client, company  # noqa: F401  Isolated environment before app imports.
from test_accounts import setup

RFC = 'SSI260101AB1'
MASTER = 'Maestra-Sintetica-2026!'


def office(c):
    cid = company(c, name='Servicios Sintéticos', rfc=RFC).json()['id']
    other = company(c, name='Sin Firma', rfc='SFI260101AB1').json()['id']
    setup(c)
    assert c.post('/api/credentials/vault/setup', json={'password': MASTER, 'confirm': MASTER}).status_code == 201
    return cid, other


def upload(c, cid, cer, key, klass='FIEL_EMPRESA', **form):
    r = c.post(
        f'/api/credentials/companies/{cid}/certificates/upload',
        files={'cer': ('f.cer', cer, 'application/octet-stream'), 'key': ('f.key', key, 'application/octet-stream')},
        data={'password': 'Llave-Sintetica-1', 'cert_class': klass, **form},
    )
    assert r.status_code == 201, r.text
    return r.json()['id']


def test_list_carries_certificates_badges_and_indicators(client):  # noqa: F811
    cid, other = office(client)
    soon = pair(end=20, number='30001000000500000020', seed='pronto')
    fiel = upload(client, cid, soon[0], soon[1])
    csd = pair(branch='MATRIZ', number='30001000000500000021')
    upload(client, cid, csd[0], csd[1], 'CSD')
    weak = client.post(f'/api/credentials/companies/{cid}/secrets', json={'kind': 'SAT_CIEC', 'secret': '123456'})
    client.post(f'/api/credentials/companies/{cid}/secrets/{weak.json()["id"]}/reveal', json={'action': 'copy'})
    body = client.get('/api/credentials/vault').json()
    assert 'envelope' not in str(body) and 'Llave-Sintetica' not in str(body)
    companies = {c['id']: c for c in body['companies']}
    assert companies[cid]['fiel']['state'] == 'expiring' and companies[cid]['fiel']['days'] in (19, 20)
    assert companies[other]['fiel'] == {'state': 'none', 'days': None}
    assert companies[cid]['certificate_count'] == 2 and companies[cid]['password_count'] == 1
    assert companies[cid]['person_type'] == 'Moral' and companies[cid]['regime']
    cards = {c['cert_class']: c for c in body['certificates']}
    assert cards['FIEL_EMPRESA']['id'] == fiel and cards['FIEL_EMPRESA']['validity'] == 'expiring'
    assert cards['FIEL_EMPRESA']['files'] == {'cer': 'f.cer', 'key': 'f.key'}
    assert cards['CSD']['branch'] == 'MATRIZ' and cards['CSD']['validity'] == 'valid'
    s = body['summary']
    assert (s['passwords'], s['certificates'], s['expiring'], s['weak_or_repeated']) == (1, 2, 1, 1)
    assert s['last_access']['kind'] == 'COPIAR' and s['last_access']['what'] == 'SAT_CIEC'


def test_delete_certificate_keeps_history(client):  # noqa: F811
    cid, _ = office(client)
    cer, key, _ = pair()
    ident = upload(client, cid, cer, key)
    assert client.delete(f'/api/credentials/companies/{cid}/certificates/{ident}').status_code == 200
    body = client.get('/api/credentials/vault').json()
    [card] = [c for c in body['certificates'] if c['id'] == ident]
    assert card['active'] is False
    assert not [i for i in body['items'] if i['id'] == card['key_password_id']]  # its key password is archived
    assert body['companies'][0]['fiel']['state'] == 'none'
    assert client.delete(f'/api/credentials/companies/{cid}/certificates/no-existe').status_code == 404
