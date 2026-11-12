import io
from pathlib import Path
from dataclasses import replace
import pytest
from sqlalchemy import select
from test_storage_core import core, ADMIN, actor, XML
from app.models import StorageSource, StorageIndexJob, Document
from app.storage.smb import WindowsSMBProvider, unc_root, windows_root
from app.storage.local import LocalFolderProvider
from app.storage.connector import ConnectorService
from app.storage.router import SourceConfiguration
from app.storage.indexer import LocalIndexer
from app.storage.providers import StorageError, Availability


@pytest.mark.parametrize('value', [r'C:\data', r'\\?\UNC\server\share', r'\\.\share\x',
    r'\\server\share\..\escape', r'\\server\share\a:secret', r'\\server\share\folder.'])
def test_unc_rejects_unsafe_syntax(value):
    with pytest.raises(StorageError):
        unc_root(value)


def test_unc_authorization_precedes_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('Unapproved network path was touched')
    monkeypatch.setattr(Path, 'lstat', forbidden)
    monkeypatch.setattr(Path, 'resolve', forbidden)
    for root in [r'\\other\share\clients', r'\\server\share\clients-other', r'\\server\other\clients']:
        with pytest.raises(StorageError, match='unauthorized_root'):
            WindowsSMBProvider(root, (Path(r'\\server\share\clients'),))
    assert windows_root(dict(server='server',share='share',subdirectory='clients\\2026')) == unc_root(r'\\SERVER\SHARE\clients\2026')


def payload(**kwargs):
    return SourceConfiguration(label='SMB test',kind='windows_smb',
        windows=dict(server='server',share='share',subdirectory='clients'),**kwargs)


def test_smb_settings_dotenv_roundtrip(tmp_path,monkeypatch):
    from dotenv import dotenv_values,set_key
    from app.storage.settings import StorageSettings
    import json
    env=tmp_path/'.env'
    env.write_text('EXISTING=preserved\n',encoding='utf-8')
    value=json.dumps(['//server/share/clients'])
    set_key(str(env),'CS_STORAGE_SMB_ALLOWED_ROOTS',value,quote_mode='always')
    monkeypatch.setenv('CS_STORAGE_SMB_ALLOWED_ROOTS',dotenv_values(env)['CS_STORAGE_SMB_ALLOWED_ROOTS'])
    monkeypatch.setenv('CS_STORAGE_ALLOWED_ROOTS','[]')
    settings=StorageSettings.from_environment(tmp_path)
    assert unc_root(settings.smb_allowed_roots[0])==unc_root(r'\\server\share\clients')
    assert dotenv_values(env)['EXISTING']=='preserved'


def test_smb_connector_index_integrity_and_schedule(core,monkeypatch):
    service,sessions,root=core
    (root/'a.xml').write_bytes(XML)
    (root/'private.key').write_bytes(b'private key must never be enumerated')
    (root/'bundle.zip').write_bytes(b'private containers excluded')
    # Exercise the real queue/observations/download path against a disposable transport.
    monkeypatch.setattr(service,'_smb',lambda windows,exclusions=(): LocalFolderProvider(root,(root,),exclusions=exclusions))
    connector=ConnectorService(service)
    saved=connector.save(ADMIN,payload(interval_minutes=5))
    ident=saved['id']
    assert connector.probe(ADMIN,ident)['state']=='available'
    with pytest.raises(StorageError,match='duplicate_source'):
        connector.save(ADMIN,payload())
    indexer=LocalIndexer(service)
    indexer.enqueue(ADMIN,ident)
    job=indexer.claim('smb-test')
    indexer.run(job,'smb-test')
    with sessions() as db:
        assert db.get(StorageIndexJob,job).status=='completed'
        documents=list(db.scalars(select(Document)))
        assert len(documents)==1
        doc_id=documents[0].id
    with service.read(ADMIN,doc_id) as content:
        assert content.stream.read()==XML
    from app.models import now
    from datetime import timedelta
    with sessions.begin() as db:
        db.get(StorageSource,ident).next_scan_at=now()-timedelta(seconds=1)
    assert indexer.tick('smb-test')==1
    assert indexer.tick('smb-test')==0
    job=indexer.claim('smb-test')
    indexer.run(job,'smb-test')
    connector.save(ADMIN,payload(enabled=False,revision=1),ident)
    assert connector.probe(ADMIN,ident)['state']=='pending_configuration'
    with pytest.raises(StorageError):
        indexer.enqueue(ADMIN,ident)


def test_smb_disconnect_does_not_mark_documents_missing(core,monkeypatch):
    service,sessions,root=core
    (root/'a.xml').write_bytes(XML)
    provider=LocalFolderProvider(root,(root,))
    monkeypatch.setattr(service,'_smb',lambda *args:provider)
    connector=ConnectorService(service)
    ident=connector.save(ADMIN,payload())['id']
    indexer=LocalIndexer(service)
    for disconnected in [False,True]:
        if disconnected:
            monkeypatch.setattr(provider,'availability',lambda:Availability('unavailable','read_error'))
        indexer.enqueue(ADMIN,ident)
        job=indexer.claim('test')
        indexer.run(job,'test')
    from app.models import DocumentLocation
    with sessions() as db:
        assert db.get(StorageIndexJob,job).status=='failed'
        assert db.scalar(select(DocumentLocation)).availability!='missing'
    with pytest.raises(StorageError,match='forbidden'):
        connector.save(actor('company-a','read'),payload())
