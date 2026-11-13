"""Publish counts only. Private source metadata, credentials and database dumps stay private."""
from pathlib import Path
import hashlib,json,zipfile,difflib,ast
ROOT=Path(__file__).resolve().parents[1]

def main():
    run=ROOT/'.qa/pilot-first'
    if (run/'import-summary.json').exists():raise SystemExit('Historical analysis report is frozen after import; consult the authorized-import report.')
    backup=Path((ROOT/'.qa/pilot-authorized/backup-location.txt').read_text())
    result=json.loads((run/'summary-anonymized.json').read_text());checks=json.loads((run/'checks-final.json').read_text())
    assert result['analysed']==result['total'] and checks['companies']==checks['documents']==0
    assert 'identity_candidates' not in result
    integrity=result['integrity'];assert not any(integrity[k] for k in ['changed','unavailable','new_files_after_inventory','missing_files_after_inventory','final_scan_issues'])
    baseline=json.loads((backup/'baseline.json').read_text())
    header='## Primera carpeta autorizada · análisis por lotes\n\nConsultar docs/CS_PILOT_PRIMERA_CARPETA.md. El usuario autorizó la primera carpeta de EMPRESAS PRUEBA; análisis completo con staging privado, sin importación definitiva. Acceso separado 8062. No analizar la segunda carpeta ni usar el lanzador antiguo 8000 para este piloto. Conservar la confirmación humana y los límites/documentación del análisis masivo. No compartir .qa/pilot-first, credenciales, dumps ni metadatos fiscales.\n\n---\n\n'
    for name in ['AGENTS.md','CONTINUAR_EN_CODEX.md']:
        p=ROOT/name
        if name not in baseline:
            original=p.read_bytes()
            with zipfile.ZipFile(backup/'before.zip','a',zipfile.ZIP_DEFLATED) as z:z.writestr(name,original)
            baseline[name]=hashlib.sha256(original).hexdigest()
        if not p.read_text(encoding='utf-8-sig').startswith('## Primera carpeta autorizada'):
            p.write_text(header+p.read_text(encoding='utf-8-sig'),encoding='utf-8')
    (backup/'baseline.json').write_text(json.dumps(baseline,indent=2),encoding='utf-8')
    counts=result['counts'];types=result['types'];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    text=f'''# Primera carpeta autorizada — análisis completo, importación pendiente

Se utilizó exclusivamente la primera carpeta del directorio autorizado por el usuario. Se trata su contenido como sensible, aunque se haya denominado carpeta de prueba. No se analizó el contenido de la segunda carpeta en esta ejecución. No se modificaron originales, bases anteriores, .env, agent/config.json, SMB/SAT ni infraestructura del despacho.

## Resultado anonimizado

| Concepto | Cantidad |
|---|---:|
| Documentos admitidos inventariados P-01 | {result['total']} |
| Documentos procesados | {result['analysed']} |
| Clasificados por contenido (sugerencias) | {counts.get('classified',0)} |
| Sin clasificación reconocida | {counts.get('unclassified',0)} |
| Errores de lectura/extracción/formato | {counts.get('errors',0)} |
| Documentos con contenido duplicado | {counts.get('duplicates',0)} |
| Documentos con conflicto de UUID | {counts.get('conflicts',0)} |
| Empresas creadas / documentos importados definitivamente | 0 / 0 |

Tipos sugeridos: {json.dumps(types,ensure_ascii=False)}. Duplicados y conflictos son indicadores que pueden solaparse; no deben sumarse como archivos adicionales. Todos los RFC/nombres detectados son candidatos, incluidas contrapartes: no se seleccionó una empresa por nombre de carpeta ni por frecuencia. Clasificar no verifica cumplimiento fiscal ni autenticidad SAT. PDF escaneado/OCR y documentos complejos siguen sujetos a revisión.

Errores por código: {json.dumps(result.get('error_codes',{}),ensure_ascii=False)}. El archivo sin huella superó el límite de tamaño y no se abrió su contenido. El filtro de tipo desconocido incluye tanto documentos sin clasificación reconocida como los que tienen error de formato.

## Integridad

Huellas SHA-256 contrastadas de nuevo: {integrity['matched_sha256']}. Cambios de contenido detectados: {integrity['changed']}. Archivos no disponibles: {integrity['unavailable']}. Errores sin huella: {integrity['unhashed_errors']}. Archivos nuevos/faltantes al repetir el inventario: {integrity['new_files_after_inventory']} / {integrity['missing_files_after_inventory']}. Incidencias del recorrido final: {integrity['final_scan_issues']}. Sólo se leyeron PDF/XML/CER admitidos; KEY, credenciales, contenedores privados, secretos y respaldos permanecieron excluidos. Los archivos demasiado grandes o no interpretables no se presentan como verificados.

## Implementación y privacidad

Se reutilizan reconcile_sessions/reconcile_rows/reconcile_history como staging; no hay un catálogo fiscal paralelo. Inventario persistente, checkpoints cada 100 registros, reanudación comprobada tras detener un trabajador identificado y bloqueo PostgreSQL exclusivo para impedir ejecuciones simultáneas. El extractor corre en un proceso limitado a 384 MB, se recicla cada 100 extracciones y tiene timeout por operación. La caché distingue huella y extensión; no se fusionan documentos por contenido ni UUID. La detección global de duplicados/conflictos incluye todos los lotes.

Se creó un clúster PostgreSQL privado y una base exclusiva, con ACL limitada al usuario y SYSTEM, escucha loopback y una cuenta personal nueva de la aplicación. Autenticación, autorización, CSRF y auditoría existentes siguen activas. La vista previa requiere administrador personal y está paginada (50 por defecto, máximo 100); las respuestas no se almacenan en caché. No se tomaron capturas empresariales ni se publicaron RFC, nombres, UUID, archivos o credenciales en el informe compartible.

Se comprobó por HTTP: acceso anónimo 401, página sobredimensionada 422, confirmación mediante importador anterior 404 y Host no autorizado 400. La importación definitiva masiva permanece deshabilitada: esta tarea deja análisis y revisión, no empresas creadas ni documentos vinculados. Hace falta implementar/validar la fase de revisión y confirmación masiva antes de habilitarla; no debe usarse una confirmación del importador pequeño para saltar este límite.

La pantalla permite filtrar conflictos UUID, duplicados, errores y tipo desconocido, con totales y paginación calculados en backend. Los filtros se comprobaron contra PostgreSQL privado publicando únicamente sus conteos.

## Pruebas y respaldos

- 30 pruebas sintéticas del lote/piloto/importador aprobadas; 14 dirigidas de alcance e identidad aprobadas (se solapan).
- Suite backend completa: 198 aprobadas, 1 omitida, 169 advertencias. La omisión es por privilegios de enlaces; advertencias de reflexión SQLite/deprecación conservadas.
- Después se repitieron las 4 pruebas dirigidas del módulo para los últimos filtros; no se presenta la suite completa como repetida tras ese ajuste.
- TypeScript sin emisión y build Vite aprobados; permanece advertencia de chunk >500 KB.
- La primera ejecución dirigida detectó un problema de codificación al editar un archivo: se restauró UTF-8 desde el respaldo y se repitieron las pruebas correctamente.
- Respaldo de esquema vacío anterior a la lectura documental restaurado en una base nueva. Respaldo de vista previa final también restaurado en otra base nueva; {checks['restored_staging_rows']} filas de staging y sus contenidos/auditoría contrastados por SHA-256, sin sobrescribir el origen. SHA del dump final: {checks['backup_sha256']}.
- No se considera ejecutada QA visual con datos reales: deliberadamente se evita su captura. La nueva pantalla fue comprobada por tipos/build y contratos HTTP; aceptación visual privada pendiente.

El respaldo de fuentes está en `{backup.name}` bajo RESPALDOS, con before.zip, baseline.json, final.json, changes.json y diff. Inventario exacto: CS_PILOT_BATCH_FILES.md. Se conservan los resultados anonimizados junto al respaldo. Los archivos operativos privados y dumps están bajo .qa/pilot-first: **no adjuntarlos a Claude ni a entregas compartidas**.

## Acceso y recuperación

Usar ABRIR_PILOTO_PRIMERA_CARPETA.cmd o http://127.0.0.1:8062. Entrar con la cuenta del archivo local protegido .qa/pilot-first/access.json (no incluido en este informe). Empresas → Importar y conciliar → Fuente → Primera carpeta · análisis por lotes. El puerto 8000 y el piloto sintético 8060 son entornos diferentes.

Para revertir código, detener exclusivamente los procesos del piloto, comparar final.json y preservar cambios posteriores; recuperar los modificados desde before.zip y conservar los añadidos antes de retirarlos. Recuperar el build anterior como conjunto. No superponer carpetas sobre datos o configuración. Para recuperar el staging, restaurar el dump en una base NUEVA y verificar huellas, conteos y conexión antes de usarla; no restaurar sobre producción ni eliminar historial.

Lote 5 no iniciado. ContaSuite v1.0 continúa sin aprobación operativa; permanecen las validaciones de SCM, TLS/LAN, Windows limpio, accesibilidad y aceptación integral.
'''
    (ROOT/'docs/CS_PILOT_PRIMERA_CARPETA.md').write_text(text,encoding='utf-8')
    claude=ROOT/'docs/REPORTE_PARA_CLAUDE_2026-11-12.md'
    notice='> Actualización posterior a este corte: ya se autorizó y analizó la primera carpeta. Consultar CS_PILOT_PRIMERA_CARPETA.md para los resultados anonimizados y pendientes actuales. El informe siguiente se conserva como antecedente.\n\n'
    if claude.is_file() and not claude.read_text(encoding='utf-8').startswith('> Actualización posterior'):
        claude.write_text(notice+claude.read_text(encoding='utf-8'),encoding='utf-8')
    dist=ROOT/'frontend/dist';hashes={p.relative_to(dist).as_posix():sha(p) for p in dist.rglob('*') if p.is_file() and p.name!='contasuite-build.json'}
    (dist/'contasuite-build.json').write_text(json.dumps({'task':'CS-PILOT-FIRST-BATCH','production_approved':False,'features':['private_batch_preview'],'files':hashes},indent=2),encoding='utf-8')
    names=set(baseline)|{'ABRIR_PILOTO_PRIMERA_CARPETA.cmd','docs/CS_PILOT_BATCH_FILES.md'}
    for folder in ['backend','frontend/src','frontend/dist','scripts','docs']:
        names.update(p.relative_to(ROOT).as_posix() for p in (ROOT/folder).rglob('*') if p.is_file() and not set(p.parts)&{'__pycache__','.pytest_cache','node_modules'} and p.suffix!='.pyc')
    inventory='docs/CS_PILOT_BATCH_FILES.md';changes={}
    for n in sorted(names):
        value=sha(ROOT/n) if (ROOT/n).is_file() else None
        if value!=baseline.get(n) or n==inventory:changes[n]={'status':'added' if n not in baseline else 'deleted' if value is None else 'modified','before':baseline.get(n),'after':value}
    lines=['# Inventario de análisis por lotes — primera carpeta','','Excluye datos, configuración, dumps, credenciales, dependencias y .qa.','']
    for status in ['modified','added','deleted']:lines.extend([f'## {status}','',*[f'- `{n}`' for n,v in changes.items() if v['status']==status],''])
    (ROOT/inventory).write_text('\n'.join(lines),encoding='utf-8');changes[inventory]['after']=sha(ROOT/inventory)
    final={n:sha(ROOT/n) for n in sorted(names) if (ROOT/n).is_file()}
    for n in changes:
        if n.endswith('.py') and (ROOT/n).is_file():ast.parse((ROOT/n).read_text(encoding='utf-8-sig'))
    (backup/'changes.json').write_text(json.dumps(changes,indent=2),encoding='utf-8');(backup/'final.json').write_text(json.dumps(final,indent=2),encoding='utf-8')
    diff=[]
    with zipfile.ZipFile(backup/'before.zip') as z:
        assert z.testzip() is None
        assert all(hashlib.sha256(z.read(n)).hexdigest()==h for n,h in baseline.items())
        for n,v in changes.items():
            if n.startswith('frontend/dist/') or n.endswith(('.jpg','.png')):diff.append('Generated/binary change: '+n+'\n');continue
            old=z.read(n).decode('utf-8-sig') if v['before'] else '';new=(ROOT/n).read_text(encoding='utf-8-sig') if v['after'] else ''
            diff.extend(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='before/'+n,tofile='after/'+n))
    (backup/'batch.diff').write_text(''.join(diff),encoding='utf-8')
    safe=backup/'results';safe.mkdir(exist_ok=True)
    (safe/'summary-anonymized.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    (safe/'checks-final.json').write_text(json.dumps(checks,indent=2),encoding='utf-8')
    (safe/'backup-sha256.txt').write_text(sha(backup/'before.zip'),encoding='ascii')
    print('Anonymized report, verified source backup and inventory prepared. Files changed:',len(changes))
if __name__=='__main__':main()
