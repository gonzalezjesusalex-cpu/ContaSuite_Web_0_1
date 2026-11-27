"""Declara en modo carpeta (rediseño del 26/11/2026, sección 4): el agente trabaja sobre la carpeta real.

Todo pasa por aquí: validación de rutas contra las raíces autorizadas, conversión de unidades mapeadas a UNC, rutas
largas, índice incremental, bloqueo con latido, respaldo, renombrado en dos fases (el `execute_renames` original),
registro para deshacer y vista previa de un PDF. Los archivos internos viven en `.declara\\` dentro de la carpeta, que el
motor ignora porque sólo lista archivos directos.

Nunca se sobrescribe un archivo y nunca se sale de las raíces que manda el servidor.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import time
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path, PureWindowsPath

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))

from app import declara_engine as motor  # noqa: E402

INTERNAL = '.declara'
INDEX = 'indice.json'
REGISTRY = 'registro.json'
LOCK = 'bloqueo'
BACKUPS = 'respaldos'
LOCK_TTL = timedelta(minutes=2)
LOCK_RENEW_SECONDS = 30
LONG_PATH = 240
MAX_ENTRIES = 5000
RETRIES = 3
RETRY_WAIT = 1.0


class FolderError(Exception):
    """A data-free reason the web can show (see REASONS in agent.py)."""

    def __init__(self, code, detail=''):
        super().__init__(code)
        self.code = code
        self.detail = detail


def now():
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------- rutas


def universal_name(path: str) -> str:
    """`Z:\\x` → `\\\\servidor\\recurso\\x` con WNetGetUniversalNameW. Sin unidad de red, la ruta queda igual."""
    if os.name != 'nt' or not (len(path) >= 2 and path[1] == ':'):
        return path
    import ctypes
    from ctypes import wintypes

    size = wintypes.DWORD(4096)
    buffer = ctypes.create_string_buffer(size.value)
    mpr = ctypes.WinDLL('mpr')
    # UNIVERSAL_NAME_INFO_LEVEL = 1; the buffer starts with a pointer to the UNC string.
    status = mpr.WNetGetUniversalNameW(ctypes.c_wchar_p(path), 1, buffer, ctypes.byref(size))
    if status != 0:
        return path
    pointer = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_wchar_p)).contents
    return pointer.value or path


def normalized(path: str) -> str:
    return str(PureWindowsPath(str(path).strip().replace('/', '\\'))).rstrip('\\').casefold()


class Guard:
    """Sólo rutas absolutas, sin «..», dentro de las raíces del servidor y ya convertidas a UNC."""

    def __init__(self, roots, resolver=universal_name):
        self.resolver = resolver
        self.roots = [self.resolver(str(r)) for r in roots or []]

    def check(self, raw: str) -> str:
        text = str(raw or '').strip().replace('/', '\\')
        win = PureWindowsPath(text)
        if not text or len(text) > 1000 or '..' in win.parts or not (win.drive and win.root):
            raise FolderError('invalid_path')
        resolved = str(PureWindowsPath(self.resolver(text))).rstrip('\\')
        if resolved.endswith(':'):
            resolved += '\\'
        target = normalized(resolved)
        if not any(target == normalized(r) or target.startswith(normalized(r) + '\\') for r in self.roots):
            raise FolderError('unauthorized_root')
        return resolved


def io_path(path) -> Path:
    """Ruta usable aunque pase de 260 caracteres: prefijo `\\\\?\\` o `\\\\?\\UNC\\` en Windows."""
    text = str(path)
    if os.name != 'nt' or text.startswith('\\\\?\\') or len(text) < LONG_PATH:
        return Path(text)
    return Path('\\\\?\\UNC\\' + text[2:] if text.startswith('\\\\') else '\\\\?\\' + text)


def internal(folder) -> Path:
    return io_path(folder) / INTERNAL


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return default


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    os.replace(temporary, path)


def hide(folder: Path):
    if os.name == 'nt':
        try:
            import ctypes

            ctypes.windll.kernel32.SetFileAttributesW(str(folder), 0x2)  # FILE_ATTRIBUTE_HIDDEN
        except OSError:
            pass


def retried(action, *args):
    """Archivo en uso por otro usuario: 3 intentos con espera antes de rendirse."""
    for attempt in range(RETRIES):
        try:
            return action(*args)
        except PermissionError:
            if attempt == RETRIES - 1:
                raise
            time.sleep(RETRY_WAIT)


# ---------------------------------------------------------------- bloqueo


def read_lock(folder):
    data = read_json(internal(folder) / LOCK, None)
    if not isinstance(data, dict):
        return None
    try:
        beat = datetime.fromisoformat(data['latido'])
    except (KeyError, ValueError):
        return None
    return {**data, 'vigente': now() - beat < LOCK_TTL}


def lock_state(folder, user, machine):
    lock = read_lock(folder)
    if not lock or not lock['vigente']:
        return {'estado': 'libre'}
    mine = lock.get('usuario') == user and lock.get('equipo') == machine
    return {
        'estado': 'propio' if mine else 'ajeno',
        'usuario': lock.get('usuario'),
        'equipo': lock.get('equipo'),
        'desde': lock.get('hora'),
    }


HELD: dict[str, dict] = {}


def take_lock(folder, user, machine):
    """El bloqueo propio se toma o se renueva; uno ajeno vigente deja la carpeta en sólo lectura."""
    state = lock_state(folder, user, machine)
    if state['estado'] == 'ajeno':
        return state
    path = internal(folder)
    current = read_lock(folder)
    since = current['hora'] if current and state['estado'] == 'propio' else now().isoformat()
    write_json(path / LOCK, {'usuario': user, 'equipo': machine, 'hora': since, 'latido': now().isoformat()})
    hide(path)
    HELD[normalized(folder)] = {'folder': str(folder), 'user': user, 'machine': machine, 'used': time.monotonic()}
    return lock_state(folder, user, machine)


def release_lock(folder, user, machine):
    HELD.pop(normalized(folder), None)
    if lock_state(folder, user, machine)['estado'] == 'propio':
        try:
            (internal(folder) / LOCK).unlink()
        except OSError:
            pass
    return lock_state(folder, user, machine)


def renew_held(idle_seconds=150):
    """Llamado por el ciclo del agente: renueva cada 30 s los bloqueos en uso y suelta los abandonados."""
    for key, held in list(HELD.items()):
        if time.monotonic() - held['used'] > idle_seconds:
            release_lock(held['folder'], held['user'], held['machine'])
            continue
        try:
            if lock_state(held['folder'], held['user'], held['machine'])['estado'] != 'ajeno':
                data = read_json(internal(held['folder']) / LOCK, {})
                data['latido'] = now().isoformat()
                write_json(internal(held['folder']) / LOCK, data)
        except OSError:
            HELD.pop(key, None)


# ---------------------------------------------------------------- lectura de carpetas


def pdf_files(folder):
    base = io_path(folder)
    entries = []
    for n, entry in enumerate(os.scandir(base)):
        if n >= MAX_ENTRIES:
            raise FolderError('demasiados_archivos')
        if entry.is_file(follow_symlinks=False):
            entries.append(entry)
    return entries


def list_roots(guard: Guard):
    rows = []
    for root in guard.roots:
        try:
            available = io_path(root).is_dir()
        except OSError:
            available = False
        rows.append({'ruta': root, 'red': root.startswith('\\\\'), 'disponible': available})
    return rows


def list_folder(guard: Guard, raw, user, machine, template=''):
    folder = guard.check(raw)
    try:
        children = sorted(
            (e for e in os.scandir(io_path(folder)) if e.is_dir(follow_symlinks=False) and e.name != INTERNAL),
            key=lambda e: e.name.casefold(),
        )[:500]
    except FileNotFoundError:
        raise FolderError('missing') from None
    except PermissionError:
        raise FolderError('access_denied') from None
    rows = []
    for child in children:
        path = os.path.join(folder, child.name)
        try:
            pdfs = sum(1 for e in os.scandir(io_path(path)) if e.is_file() and e.name.lower().endswith('.pdf'))
            readable = True
        except OSError:
            pdfs, readable = 0, False
        rows.append(
            {
                'nombre': child.name,
                'ruta': path,
                'pdf': pdfs,
                'legible': readable,
                'indice': readable and (internal(path) / INDEX).exists(),
                'plantilla': bool(template) and normalized(path) == normalized(template),
                'bloqueo': lock_state(path, user, machine) if readable else {'estado': 'libre'},
            }
        )
    parent = str(PureWindowsPath(folder).parent)
    in_roots = True
    try:
        guard.check(parent)
    except FolderError:
        in_roots = False
    return {
        'ruta': folder,
        'padre': parent if in_roots and normalized(parent) != normalized(folder) else None,
        'carpetas': rows,
        'pdf': sum(1 for e in pdf_files(folder) if e.name.lower().endswith('.pdf')),
        'bloqueo': lock_state(folder, user, machine),
    }


def probe(guard: Guard, raw, user, machine):
    """Probar conexión: lectura, escritura (crea y borra `.declara\\.prueba`), latencia y bloqueo."""
    folder = guard.check(raw)
    result = {'ruta': folder, 'lectura': False, 'escritura': False, 'latencia_ms': None, 'bloqueo': None}
    started = time.perf_counter()
    try:
        pdf_files(folder)
        result['lectura'] = True
    except FileNotFoundError:
        raise FolderError('missing') from None
    except PermissionError:
        raise FolderError('access_denied') from None
    result['latencia_ms'] = round((time.perf_counter() - started) * 1000)
    try:
        test = internal(folder) / '.prueba'
        test.parent.mkdir(exist_ok=True)
        hide(test.parent)
        test.write_bytes(b'ok')
        test.unlink()
        result['escritura'] = True
    except OSError:
        result['escritura'] = False
    result['bloqueo'] = lock_state(folder, user, machine)
    return result


def signature(guard: Guard, raw):
    """Firma barata de la carpeta (nombres, tamaños y fechas): sirve para avisar de cambios sin leer los PDF."""
    folder = guard.check(raw)
    digest = hashlib.sha256()
    count = 0
    for entry in sorted(pdf_files(folder), key=lambda e: e.name.casefold()):
        info = entry.stat()
        digest.update(f'{entry.name}\0{info.st_size}\0{info.st_mtime_ns}\n'.encode())
        count += 1
    return {'ruta': folder, 'firma': digest.hexdigest(), 'archivos': count}


# ---------------------------------------------------------------- análisis con índice incremental


def analyze(guard: Guard, raw, short_name, expected_rfc, user, machine):
    folder = guard.check(raw)
    entries = pdf_files(folder)
    index_path = internal(folder) / INDEX
    index = read_json(index_path, {})
    previous = index.get('archivos', {}) if index.get('nombre_corto') == short_name else {}
    fresh, reused = {}, 0
    stats = {e.name: e.stat() for e in entries}

    def key(path):
        info = stats.get(path.name)
        return (info.st_size, info.st_mtime_ns) if info else None

    original_parse, original_hash = motor.parse_pdf, motor.sha256_file
    parsed = {}

    def unchanged(path):
        old = previous.get(path.name)
        return old if old and key(path) == (old['tamano'], old['modificado']) else None

    def cached_parse(path, company):
        # What `parse_pdf` returns depends only on the file and the short name; `analyze_folder` decides the rest
        # (copies, collisions, RESICO numbering, RFC) on every run. The raw result is kept before it changes it.
        nonlocal reused
        old = unchanged(path)
        if old and old.get('info'):
            reused += 1
            parsed[path.name] = old['info']
            return motor.PdfInfo(**{**old['info'], 'path': path})
        info = original_parse(path, company)
        parsed[path.name] = {k: v for k, v in asdict(info).items() if k != 'path'}
        return info

    def cached_hash(path):
        old = unchanged(path)
        return old['sha256'] if old and old.get('sha256') else original_hash(path)

    # The engine itself runs unchanged; only its file reads come from the index when nothing changed.
    motor.parse_pdf, motor.sha256_file = cached_parse, cached_hash
    try:
        infos = motor.analyze_folder(io_path(folder), short_name, expected_rfc)
    finally:
        motor.parse_pdf, motor.sha256_file = original_parse, original_hash
    for info in infos:
        info.sha256 = info.sha256 or cached_hash(info.path)
        size, mtime = key(info.path)
        fresh[info.path.name] = {
            'tamano': size,
            'modificado': mtime,
            'sha256': info.sha256,
            'info': parsed.get(info.path.name),
        }
    lock = take_lock(folder, user, machine)
    read_only = lock['estado'] == 'ajeno'
    if not read_only:
        try:
            write_json(index_path, {'nombre_corto': short_name, 'actualizado': now().isoformat(), 'archivos': fresh})
            hide(internal(folder))
        except OSError:
            pass
    return {
        'ruta': folder,
        # Sin campos vacíos: el resultado viaja como JSON y una carpeta grande no debe pasar del límite.
        'registros': [
            {k: v for k, v in {**asdict(i), 'path': i.path.name}.items() if v not in (None, '', False)} for i in infos
        ],
        'nombres': sorted(e.name for e in entries),
        'leidos': len(infos) - reused,
        'total': len(infos),
        'firma': signature(guard, folder)['firma'],
        'bloqueo': lock,
        'solo_lectura': read_only,
        'deshacer': bool(read_json(internal(folder) / REGISTRY, [])),
    }


# ---------------------------------------------------------------- vista previa, aplicar y deshacer


def read_pdf(guard: Guard, raw, name, sha):
    folder = guard.check(raw)
    if PureWindowsPath(name).name != name or not name.lower().endswith('.pdf'):
        raise FolderError('invalid_path')
    path = io_path(folder) / name
    data = retried(path.read_bytes)
    if hashlib.sha256(data).hexdigest() != sha:
        raise FolderError('cambio_externo')
    return data


def long_names(folder, plan):
    return [p['destino'] for p in plan if len(os.path.join(str(folder), p['destino'])) > LONG_PATH]


def check_plan(folder, plan):
    names = set()
    for item in plan:
        for key in ('origen', 'destino'):
            value = item.get(key) or ''
            if PureWindowsPath(value).name != value or motor.INVALID_FILENAME_CHARS.search(value) or not value:
                raise FolderError('invalid_path')
        if item['destino'].casefold() in names:
            raise FolderError('destinos_duplicados')
        names.add(item['destino'].casefold())


def apply_plan(guard: Guard, raw, plan, backup, user, machine):
    """Renombra en la misma carpeta: verifica huellas, respalda, renombra en dos fases y registra el lote."""
    folder = guard.check(raw)
    check_plan(folder, plan)
    if take_lock(folder, user, machine)['estado'] == 'ajeno':
        raise FolderError('carpeta_bloqueada')
    base = io_path(folder)
    pending, infos = [], []
    for item in plan:
        source = base / item['origen']
        try:
            current = retried(motor.sha256_file, source)
        except FileNotFoundError:
            raise FolderError('cambio_externo', item['origen']) from None
        except PermissionError:
            pending.append(item['origen'])
            continue
        if current != item['sha256']:
            raise FolderError('cambio_externo', item['origen'])
        infos.append(motor.PdfInfo(path=source, expected_name=item['destino'], status='RENOMBRAR'))
    copied = None
    if backup and infos:
        stamp = datetime.now().strftime('%Y-%m-%d_%H%M%S')
        copied = internal(folder) / BACKUPS / stamp
        copied.mkdir(parents=True, exist_ok=False)
        hide(internal(folder))
        for info in infos:
            target = copied / info.path.name
            retried(shutil.copy2, info.path, target)
            if motor.sha256_file(target) != motor.sha256_file(info.path):
                raise FolderError('respaldo_fallido', info.path.name)
    renamed, errors = motor.execute_renames(infos)
    if errors:
        raise FolderError('renombrado_fallido', '; '.join(errors)[:500])
    batch = {
        'lote': hashlib.sha256(f'{folder}{now().isoformat()}'.encode()).hexdigest()[:12],
        'fecha': now().isoformat(),
        'usuario': user,
        'equipo': machine,
        'respaldo': copied.name if copied else None,
        'cambios': [{'origen': i.path.name, 'destino': i.expected_name, 'sha256': None} for i in infos],
    }
    for change, item in zip(batch['cambios'], [p for p in plan if p['origen'] not in pending], strict=True):
        change['sha256'] = item['sha256']
    registry = read_json(internal(folder) / REGISTRY, [])
    write_json(internal(folder) / REGISTRY, (registry + [batch])[-50:])
    return {
        'ruta': folder,
        'renombrados': renamed,
        'pendientes': pending,
        'respaldo': copied.name if copied else None,
        'lote': batch['lote'],
    }


def undo_last(guard: Guard, raw, user, machine):
    """Deshacer último renombrado: devuelve cada archivo a su nombre anterior, aunque se haya cerrado la app."""
    folder = guard.check(raw)
    if take_lock(folder, user, machine)['estado'] == 'ajeno':
        raise FolderError('carpeta_bloqueada')
    registry = read_json(internal(folder) / REGISTRY, [])
    if not registry:
        raise FolderError('sin_registro')
    batch = registry[-1]
    base = io_path(folder)
    infos = []
    for change in batch['cambios']:
        path = base / change['destino']
        if not path.exists() or (change.get('sha256') and motor.sha256_file(path) != change['sha256']):
            raise FolderError('cambio_externo', change['destino'])
        if (base / change['origen']).exists() and change['origen'].casefold() not in {
            c['destino'].casefold() for c in batch['cambios']
        }:
            raise FolderError('destino_existe', change['origen'])
        infos.append(motor.PdfInfo(path=path, expected_name=change['origen'], status='RENOMBRAR'))
    restored, errors = motor.execute_renames(infos)
    if errors:
        raise FolderError('renombrado_fallido', '; '.join(errors)[:500])
    write_json(internal(folder) / REGISTRY, registry[:-1])
    return {'ruta': folder, 'restaurados': restored, 'lote': batch['lote'], 'cambios': batch['cambios']}


def save_downloaded(guard: Guard, raw, downloaded, short_name, rfc, user, machine):
    """Guardar y renombrar en un paso un PDF que llegó del SAT (sesión SAT, 4.4).

    Se copia a la carpeta con un nombre temporal, se verifican tamaño y SHA-256 y el motor (con el índice) decide su
    nombre estándar contra la carpeta actual, con consecutivo si hace falta. Nunca se sobrescribe un archivo.
    Devuelve (estado, nombre): 'guardado' con su nombre final, 'ya_existia' si es copia idéntica de uno que ya está, o
    'guardado' con el nombre descargado cuando el PDF no se pudo clasificar.
    """
    folder = guard.check(raw)
    if take_lock(folder, user, machine)['estado'] == 'ajeno':
        raise FolderError('carpeta_bloqueada')
    source = Path(downloaded)
    expected_sha = motor.sha256_file(source)
    size = source.stat().st_size
    base = io_path(folder)
    temp = base / f'~SAT_{expected_sha[:16]}.pdf'
    if temp.exists():
        temp.unlink()
    with source.open('rb') as src, temp.open('xb') as out:
        shutil.copyfileobj(src, out, 1024 * 1024)
    if temp.stat().st_size != size or motor.sha256_file(temp) != expected_sha:
        temp.unlink(missing_ok=True)
        raise FolderError('copia_no_verificada')
    try:
        result = analyze(guard, folder, short_name, rfc, user, machine)
        record = next(r for r in result['registros'] if r['path'] == temp.name)
        status, name = record.get('status'), record.get('expected_name')
        if status == 'COPIA IDÉNTICA':
            temp.unlink()
            return 'ya_existia', record.get('identical_to')
        if status != 'RENOMBRAR' or not name:
            name = Path(sb_unique(base, source.name)).name
        final = base / name
        if final.exists():
            raise FolderError('destino_existe', name)
        retried(os.rename, temp, final)
        return 'guardado', name
    except Exception:
        temp.unlink(missing_ok=True)
        raise


def sb_unique(folder: Path, filename: str) -> Path:
    name = PureWindowsPath(filename).name or 'declaracion.pdf'
    if not name.lower().endswith('.pdf'):
        name += '.pdf'
    name = motor.INVALID_FILENAME_CHARS.sub(' ', name)
    target = folder / name
    n = 2
    while target.exists():
        target = folder / f'{Path(name).stem} ({n}).pdf'
        n += 1
    return target


# ---------------------------------------------------------------- entrada del agente

OPS = {
    'raices',
    'listar',
    'probar',
    'firma',
    'analizar',
    'leer_pdf',
    'aplicar',
    'deshacer',
    'liberar',
    'sat',
    'sat_estado',
    'sat_instalar',
}


def run(payload, roots, user, machine, resolver=universal_name, options=None, report=None, fetch_fiel=None):
    """Un trabajo `declara_carpeta`. Devuelve el resultado; `_pdf` (bytes) lo sube el agente aparte."""
    op = payload.get('op')
    if op not in OPS:
        raise FolderError('operacion_desconocida')
    guard = Guard(roots, resolver)
    user = user or 'usuario'
    if op in {'sat', 'sat_estado', 'sat_instalar'}:
        import sat_session

        if op == 'sat_estado':
            return sat_session.browser_state(options or {})
        if op == 'sat_instalar':
            return sat_session.install_firefox(options or {})
        return sat_session.run(payload, roots, user, machine, options or {}, report or (lambda e: {}), fetch_fiel)
    if op == 'raices':
        return {'raices': list_roots(guard)}
    path = payload.get('ruta', '')
    if op == 'listar':
        return list_folder(guard, path, user, machine, payload.get('plantilla', ''))
    if op == 'probar':
        return probe(guard, path, user, machine)
    if op == 'firma':
        result = signature(guard, path)
        folder = result['ruta']
        if normalized(folder) in HELD:
            HELD[normalized(folder)]['used'] = time.monotonic()
        result['bloqueo'] = take_lock(folder, user, machine)
        return result
    if op == 'analizar':
        return analyze(guard, path, payload['nombre_corto'], payload.get('rfc'), user, machine)
    if op == 'leer_pdf':
        data = read_pdf(guard, path, payload['nombre'], payload['sha256'])
        return {'_pdf': data, 'sha256': payload['sha256']}
    if op == 'aplicar':
        return apply_plan(guard, path, payload['plan'], bool(payload.get('respaldo', True)), user, machine)
    if op == 'deshacer':
        return undo_last(guard, path, user, machine)
    return {'bloqueo': release_lock(guard.check(path), user, machine)}
