import hashlib, json, sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from restore_postgres import verify, restore


def backup(root):
    (root / 'data').mkdir()
    (root / 'data' / 'sample.pdf').write_bytes(b'synthetic')
    (root / 'database.dump').write_bytes(b'synthetic-dump')
    manifest = {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in root.rglob('*')
        if p.is_file()
    }
    (root / 'sha256.json').write_text(json.dumps(manifest))


def test_backup_integrity_detects_changed_missing_and_extra_files(tmp_path):
    backup(tmp_path)
    assert len(verify(tmp_path)) == 2
    p = tmp_path / 'data/sample.pdf'
    p.write_bytes(b'changed')
    with pytest.raises(ValueError, match='integrity'):
        verify(tmp_path)
    p.unlink()
    with pytest.raises(ValueError, match='inventory'):
        verify(tmp_path)


def test_backup_manifest_cannot_escape_root(tmp_path):
    backup(tmp_path)
    manifest = json.loads((tmp_path / 'sha256.json').read_text())
    manifest['../outside'] = 'a' * 64
    (tmp_path / 'sha256.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        verify(tmp_path)


def test_restore_rejects_live_database_and_existing_directory_before_connecting(tmp_path):
    backup(tmp_path)
    with pytest.raises(ValueError, match='NEW'):
        restore(tmp_path, tmp_path, 'contasuite', tmp_path / 'new')
    with pytest.raises(ValueError, match='New absolute'):
        restore(tmp_path, tmp_path, 'contasuite_restore_test', tmp_path)


def test_worker_stopped_before_loop_does_not_run_jobs(monkeypatch):
    import threading
    from app.storage import worker

    event = threading.Event()
    event.set()
    monkeypatch.setattr(worker, 'run_once', lambda *a, **k: pytest.fail('Stopped worker ran a job'))
    worker.main(event, ['--mode', 'alerts'])
