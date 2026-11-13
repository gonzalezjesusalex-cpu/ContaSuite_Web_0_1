"""Test code-only update against the prior generated local installer fixture."""

import base64, hashlib, io, json, subprocess, sys, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    work = ROOT / '.qa/excel-fix-test'
    work.mkdir(exist_ok=False)
    source = work / 'setup'
    archive = ROOT.parent / 'ENTREGAS/ContaSuite_RC1_Correccion_Excel.zip'
    with zipfile.ZipFile(archive) as z:
        manifest = json.loads(z.read('PACKAGE_SHA256.json'))
        assert all(hashlib.sha256(z.read(n)).hexdigest() == v for n, v in manifest.items())
        z.extractall(source)
    target = ROOT / '.qa/local-installer-final/installed'
    assert target.is_relative_to(ROOT / '.qa') and (target / 'LOCAL_INSTALLATION.json').is_file()
    from openpyxl import Workbook

    book = Workbook()
    sheet = book.active
    sheet.append(['Empresa', 'RFC'])
    sheet.append(['Synthetic update test', 'AAA010101AA1'])
    sheet['A2'].hyperlink = 'https://example.invalid/never-request'
    stream = io.BytesIO()
    book.save(stream)
    book.close()
    payload = {'source': str(source), 'target': str(target), 'workbook': base64.b64encode(stream.getvalue()).decode()}
    code = """import base64,json,sys,hashlib,subprocess
from pathlib import Path
from local_setup import marker
from local_runtime import start,stop,alive
from secure_config import load
from apply_excel_fix import apply
from sqlalchemy import create_engine,text
v=json.load(sys.stdin);root=Path(v['target']);source=Path(v['source']);marker(root)
def counts():
 engine=create_engine(load(root/'private/service.json')['DATABASE_URL'])
 try:
  with engine.connect() as db:return [db.scalar(text('SELECT count(*) FROM '+table)) for table in ['companies','documents','document_versions','user_accounts']]
 finally:engine.dispose()
config=hashlib.sha256((root/'private/service.json').read_bytes()).hexdigest()
start(root)
try:
 before=counts();result=apply(source,root);assert result['was_running'] and alive(root)
 assert counts()==before
 assert hashlib.sha256((root/'private/service.json').read_bytes()).hexdigest()==config
 parser="import json,sys,base64;from app.company_xlsx import read_xlsx;r=read_xlsx(base64.b64decode(json.load(sys.stdin)['workbook']),'fiscal_metadata');assert len(r['rows'])==1;print('Updated installed reader accepts passive hyperlink workbook')"
 check=subprocess.run([str(root/'runtime/python.exe'),'-B','-c',parser],input=json.dumps(v),text=True,capture_output=True,timeout=60)
 assert check.returncode==0,check.stderr
 print(check.stdout)
 assert (Path(result['backup'])/'app/backend/app/company_xlsx.py').is_file()
 print(json.dumps({'updated':True,'database_counts_preserved':True,'configuration_preserved':True,'running_installation_restarted':True,'previous_code_backed_up':True,'installed_reader_test':'passed'}))
finally:stop(root)
"""
    result = subprocess.run(
        [str(source / 'runtime/python.exe'), '-B', '-c', code],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        timeout=240,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
    )
    if result.returncode:
        raise RuntimeError(result.stdout + '\n' + result.stderr)
    print(result.stdout)
    report = {
        'synthetic_only': True,
        'package_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
        'code_update': 'passed',
        'counts_and_configuration_preserved': True,
        'running_installation_restarted': True,
        'installed_hyperlink_workbook': 'passed',
        'real_workbook_examined': False,
    }
    (work / 'results.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report))


if __name__ == '__main__':
    main()
