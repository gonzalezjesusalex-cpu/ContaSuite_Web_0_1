"""Synthetic pilot only: new PostgreSQL database and generated local folders. No real paths."""
import os,sys,json,secrets,hashlib,subprocess,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from integration_runtime import ROOT,RUN as PREVIOUS,BIN,environment,call
RUN=ROOT/'.qa/pilot-import/lab'
DATABASE='contasuite_pilot_synthetic_001'

def configuration():
    config=json.loads((RUN/'synthetic.json').read_text())
    assert config['synthetic'] is True and config['database']==DATABASE
    previous=json.loads((PREVIOUS/'synthetic.json').read_text());env=environment(previous)
    env.update(DATABASE_URL=env['DATABASE_URL'].rsplit('/',1)[0]+'/'+DATABASE,DATA_DIR=str(RUN/'data'),
        APP_TOKEN=config['app_token'],AGENT_TOKEN=config['agent_token'],PYTHONPATH=str(ROOT/'backend'),
        CS_ALLOWED_HOSTS=json.dumps(['127.0.0.1','localhost']),CS_PILOT_ENABLED='1',CS_PILOT_DATABASE=DATABASE,
        CS_PILOT_ROOTS=json.dumps([str(RUN/'copies/Empresa_A'),str(RUN/'copies/Empresa_B')]),CS_STORAGE_ALLOWED_ROOTS=json.dumps([str(RUN/'copies')]))
    return config,previous,env

def original_hashes():
    return {p.relative_to(RUN/'copies').as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (RUN/'copies').rglob('*') if p.is_file()}

def main():
    mode=sys.argv[1]
    if mode=='prepare':
        assert not RUN.exists(),'Refuse to reuse existing pilot laboratory'
        previous=json.loads((PREVIOUS/'synthetic.json').read_text());environment(previous)
        import psycopg
        with psycopg.connect(host='127.0.0.1',port=previous['port'],user='recovery_test',password=previous['password'],dbname='postgres',autocommit=True) as db:
            assert Path(db.execute('SHOW data_directory').fetchone()[0]).resolve()==PREVIOUS/'cluster'
            assert not db.execute('SELECT 1 FROM pg_database WHERE datname=%s',(DATABASE,)).fetchone()
            db.execute('CREATE DATABASE '+DATABASE)
        RUN.mkdir();(RUN/'data').mkdir()
        (RUN/'synthetic.json').write_text(json.dumps(dict(synthetic=True,database=DATABASE,app_token=secrets.token_hex(32),agent_token=secrets.token_hex(32))))
        config,previous,env=configuration()
        # Only generated documents. These RFCs/names are synthetic fixtures.
        def xml(total,uuid):
            return (f'<c:Comprobante xmlns:c="http://www.sat.gob.mx/cfd/4" xmlns:t="http://www.sat.gob.mx/TimbreFiscalDigital" Fecha="2026-11-11T12:00:00" Total="{total}"><c:Emisor Rfc="AAA010101AA1" Nombre="PILOTO SINTETICO A"/><c:Receptor Rfc="BBB020202BB2" Nombre="PILOTO SINTETICO B"/><c:Complemento><t:TimbreFiscalDigital UUID="{uuid}"/></c:Complemento></c:Comprobante>').encode()
        a,b=RUN/'copies/Empresa_A',RUN/'copies/Empresa_B';(a/'CFDI').mkdir(parents=True);b.mkdir(parents=True)
        shared=xml('100','11111111-1111-1111-1111-111111111111')
        (a/'CFDI/compartido.xml').write_bytes(shared);(b/'compartido.xml').write_bytes(shared)
        for p,total in [(a,'200'),(b,'201')]: (p/'conflicto.xml').write_bytes(xml(total,'22222222-2222-2222-2222-222222222222'))
        from reportlab.pdfgen.canvas import Canvas
        c=Canvas(str(a/'constancia.pdf'));c.drawString(50,800,'CONSTANCIA DE SITUACION FISCAL - SINTETICA AAA010101AA1');c.save()
        (b/'ilegible.pdf').write_bytes(b'%PDF-1.4\nsynthetic-invalid-pdf')
        (b/'notas.txt').write_text('Unsupported synthetic content')
        (b/'credenciales').mkdir();(b/'credenciales/password.txt').write_text('SYNTHETIC NEVER READ')
        (a/'protegido.key').write_bytes(b'SYNTHETIC NEVER READ')
        (a/'.env').write_text('SYNTHETIC NEVER READ')
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes,serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID
        from datetime import datetime,timezone,timedelta
        key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        subject=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'SYNTHETIC PUBLIC CERTIFICATE')]);stamp=datetime.now(timezone.utc)
        cert=x509.CertificateBuilder().subject_name(subject).issuer_name(subject).public_key(key.public_key()).serial_number(1).not_valid_before(stamp).not_valid_after(stamp+timedelta(days=30)).sign(key,hashes.SHA256())
        (a/'publico.cer').write_bytes(cert.public_bytes(serialization.Encoding.DER))
        (RUN/'original-hashes.json').write_text(json.dumps(original_hashes(),indent=2))
        (RUN/'migration.txt').write_text(call([sys.executable,'-B',ROOT/'scripts/schema_admin.py','--data-dir',RUN/'data','--apply','--new'],env))
        # Verified, empty, schema-ready baseline before any pilot import.
        cli=env.copy();cli.update(PGHOST='127.0.0.1',PGPORT=str(previous['port']),PGUSER='recovery_test',PGPASSWORD=previous['password'])
        call([BIN/'pg_dump.exe','-Fc','--file',RUN/'before-import.dump',DATABASE],cli)
        (RUN/'baseline-backup.json').write_text(json.dumps({'database':DATABASE,'synthetic':True,'dump_sha256':hashlib.sha256((RUN/'before-import.dump').read_bytes()).hexdigest(),'originals':original_hashes()},indent=2))
        print('Exclusive synthetic pilot PostgreSQL database, local copies and hashed backup prepared.')
    config,previous,env=configuration()
    if mode in ('stop','restart'):
        pid=int((RUN/'api.pid').read_text());call(['powershell.exe','-NoProfile','-Command',f"$p=Get-CimInstance Win32_Process -Filter 'ProcessId = {pid}'; if (-not $p -or $p.CommandLine -notmatch 'uvicorn app.main:app --host 127.0.0.1 --port 8060') {{ throw 'Unexpected process' }}; Stop-Process -Id {pid} -ErrorAction Stop"])
    if mode in ('serve','restart'):
        api=subprocess.Popen([sys.executable,'-B','-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8060'],cwd=ROOT/'backend',env=env,stdout=(RUN/'api.log').open('w'),stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0));(RUN/'api.pid').write_text(str(api.pid))
        import httpx
        for _ in range(80):
            if api.poll() is not None:raise RuntimeError('Synthetic pilot startup failed')
            try:
                if httpx.get('http://127.0.0.1:8060/api/health',timeout=1).status_code==200:print('Synthetic pilot ready: http://127.0.0.1:8060');return
            except httpx.TransportError:pass
            time.sleep(.25)
        raise RuntimeError('Synthetic pilot readiness timeout')
if __name__=='__main__':main()
