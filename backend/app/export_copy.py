"""Copies the files of an export plan, verified and without ever overwriting anything.

Sources are opened through the storage provider (same link, root and change checks as the scan) and are only read.
Each file is copied to a temporary name, checked with SHA-256 against what was read, and only then renamed into
place. A name that already exists is never replaced: an identical file is skipped as a duplicate and a different one
gets a numbered name. A manifest CSV is written at the end.
"""

import hashlib
import os
import shutil
import uuid
from pathlib import Path

from .export_plan import MANIFEST_NAME, NEVER_EXTENSIONS, manifest_text
from .storage.providers import StorageError

CHUNK = 1024 * 1024
MAX_ERRORS = 30


class CopyError(Exception):
    """A copy that failed its own check; the message is shown to the person as the reason."""


def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(CHUNK), b''):
            h.update(block)
    return h.hexdigest()


def prepare_destination(destination):
    """Create the destination folder; it must not exist or must be empty. StorageError(code) otherwise."""
    destination = Path(destination)
    if destination.exists():
        if not destination.is_dir() or any(destination.iterdir()):
            raise StorageError('destino_no_vacio')
        return destination
    destination.mkdir(parents=True)  # the caller has already checked that it hangs from an authorized folder
    return destination


def _free_name(folder, name):
    stem, suffix = os.path.splitext(name)
    for n in range(2, 1000):
        candidate = folder / f'{stem} ({n}){suffix}'
        if not candidate.exists():
            return candidate
    raise StorageError('read_error')


def copy_one(provider, item, root):
    """Copy one planned file. Returns (state, reason, sha256, final path or None)."""
    folder = root.joinpath(*item.parts)
    if not folder.resolve().is_relative_to(root.resolve()):
        return 'Error', 'La carpeta de destino apunta fuera de la exportación.', '', None
    folder.mkdir(parents=True, exist_ok=True)
    temporary = folder / f'.cs-{uuid.uuid4().hex[:12]}.part'
    sha = hashlib.sha256()
    try:
        with provider.open_read(item.key) as source, open(temporary, 'xb') as out:
            for block in iter(lambda: source.read(CHUNK), b''):
                sha.update(block)
                out.write(block)
            out.flush()
            os.fsync(out.fileno())
        # open_read raises file_changed when the original changed while it was being copied.
        if digest(temporary) != sha.hexdigest():
            raise CopyError('Falló la verificación SHA-256; no se conserva la copia.')
        final = folder / item.name
        if final.exists():
            if digest(final) == sha.hexdigest():
                temporary.unlink()
                return 'Duplicado', 'Ya existe un archivo idéntico en ese lugar; se omite.', sha.hexdigest(), final
            final = _free_name(folder, item.name)
            note = 'Mismo nombre con otro contenido: se guardó con número.'
        else:
            note = 'Copia verificada con SHA-256.'
        os.rename(temporary, final)  # never replaces an existing file on Windows
        return 'Copiado', note, sha.hexdigest(), final
    except CopyError as exc:
        return 'Error', str(exc), '', None
    except StorageError as exc:
        reason = {
            'file_changed': 'El archivo cambió mientras se copiaba; se omite.',
            'access_denied': 'Windows no permitió leer el archivo.',
            'missing': 'El archivo ya no existe.',
        }.get(getattr(exc, 'code', ''), 'No se pudo copiar el archivo.')
        return 'Error', reason, '', None
    except OSError as exc:
        return 'Error', 'No se pudo escribir en el destino (' + exc.__class__.__name__ + ').', '', None
    finally:
        if temporary.exists():
            temporary.unlink(missing_ok=True)


def execute(provider, items, destination, progress=None):
    """Copy every item and write the manifest. Returns the counts and the first errors."""
    root = prepare_destination(destination)
    counts = {'Copiado': 0, 'Duplicado': 0, 'Error': 0, 'Omitido': 0}
    records, errors, copied_bytes = [], [], 0
    for n, item in enumerate(items):
        virtual = '/'.join((*item.parts, item.name))
        if Path(item.key).suffix.lower() in NEVER_EXTENSIONS:  # last line of defence: keys are never copied
            state, reason, sha, final = 'Omitido', 'Material de e.firma o llave: nunca se exporta.', '', None
        else:
            state, reason, sha, final = copy_one(provider, item, root)
        counts[state] += 1
        if state == 'Copiado':
            copied_bytes += item.size
        if state == 'Error' and len(errors) < MAX_ERRORS:
            errors.append({'p': item.key, 'motivo': reason})
        records.append((state, item.section, virtual, item.key, sha, item.size, reason))
        if progress:
            progress(n + 1, len(items))
    with open(root / MANIFEST_NAME, 'x', encoding='utf-8-sig', newline='') as f:
        f.write(manifest_text(records))
    return {
        'mode': 'apply',
        'destination': str(root),
        'copiados': counts['Copiado'],
        'duplicados': counts['Duplicado'],
        'errores': counts['Error'],
        'omitidos': counts['Omitido'],
        'bytes': copied_bytes,
        'manifiesto': MANIFEST_NAME,
        'detalle_errores': errors,
        'libre_final': shutil.disk_usage(root).free,
    }
