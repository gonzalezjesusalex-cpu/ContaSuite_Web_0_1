"""Run the existing pytest suite with fresh synthetic temp/configuration boundaries."""
import os,sys,platform,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
parent=ROOT/'.qa'/'integration-recovery-20261111-v3'/'full-suite-temp'
parent.mkdir(exist_ok=True)
os.environ.update(TMP=str(parent),TEMP=str(parent),PYTHON_DOTENV_DISABLED='1',PYTEST_DISABLE_PLUGIN_AUTOLOAD='1',
    CS_STORAGE_ALLOWED_ROOTS='[]',CS_STORAGE_SMB_ALLOWED_ROOTS='[]',SEED_DEMO='false')
tempfile.tempdir=str(parent)
# Prevent optional Windows WMI probing during imports; this is the actual test architecture.
platform.machine=lambda:'AMD64'
platform.win32_ver=lambda:('10','10.0','','')
for key in list(os.environ):
    if key.startswith(('VAULT_','CS_VAULT_','CONTA_VAULT_')):os.environ.pop(key)
sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'backend/tests')]
# test_api provisions the process-wide SQLite DB before importing app modules.
import test_api
assert str(test_api.engine.url).startswith('sqlite:///')
assert Path(test_api.TEMP.name).resolve().is_relative_to(parent)
import pytest
raise SystemExit(pytest.main([str(ROOT/'backend/tests'),'-q','--tb=short',*sys.argv[1:]]))
