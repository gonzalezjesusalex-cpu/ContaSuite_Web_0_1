"""Plan for exporting a COPY of a company's folder in the virtual order (pure logic: no file is read or written).

The originals are never touched. Every file gets a virtual path from the index of its group (CFDI by month and
emitidos/recibidos, impuestos by period, IMSS by month, nómina by quincena, expediente, estados financieros,
trabajadores); what no index places goes to «Sin clasificar» keeping its original folders. e.firma/CSD material and
password notes are NEVER part of an export. Personal data of workers is only exported when asked for.
"""

import csv
import io
import re
import unicodedata
from dataclasses import dataclass
from pathlib import PurePosixPath, PureWindowsPath

SECTIONS = {
    'cfdi': 'CFDI',
    'impuestos': 'Impuestos',
    'imss': 'IMSS',
    'nomina': 'Nómina',
    'expediente': 'Expediente de la empresa',
    'finanzas': 'Estados financieros',
    'trabajadores': 'Trabajadores',
    'sin_clasificar': 'Sin clasificar',
}
SECTION_BY_LABEL = {label: key for key, label in SECTIONS.items()}
# Workers' documents carry personal data (IDs, social security): off unless the person asks for them.
DEFAULT_INCLUDE = tuple(key for key in SECTIONS if key != 'trabajadores')
GROUP_SECTION = {
    'cfdi_xml': 'cfdi',
    'cfdi_pdf': 'cfdi',
    'sat_reportes': 'cfdi',
    'impuestos': 'impuestos',
    'imss': 'imss',
    'nomina': 'nomina',
    'legal': 'expediente',
    'identificaciones': 'expediente',
    'estados_financieros': 'finanzas',
    'trabajadores': 'trabajadores',
    'otros': 'sin_clasificar',
}
NEVER_GROUPS = {'credenciales', 'contrasenas', 'ruido'}
NEVER_EXTENSIONS = {'.key', '.pfx', '.p12', '.pem', '.req', '.sdg', '.ren', '.cer'}
MANIFEST_NAME = '_MANIFIESTO_EXPORTACION.csv'
MAX_PATH = 240  # below Windows' 260 with room for the temporary name
REASONS = {
    'destino_no_absoluto': 'El destino debe ser una ruta completa de Windows, por ejemplo C:\\Exportaciones\\Empresa.',
    'destino_unc': 'Las carpetas de red no están habilitadas para exportar.',
    'destino_invalido': 'El destino tiene caracteres que Windows no permite.',
    'destino_fuera_de_raices': 'El destino está fuera de las carpetas autorizadas por la administración.',
    'destino_dentro_origen': 'El destino no puede estar dentro de la carpeta de la empresa: la copia se mezclaría con los originales.',
    'origen_dentro_destino': 'La carpeta de la empresa no puede estar dentro del destino.',
    'destino_no_vacio': 'El destino ya existe y no está vacío. Elige una carpeta nueva: nunca se sobrescribe nada.',
}
INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
RESERVED = re.compile(r'^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\..*)?$', re.I)


@dataclass(frozen=True)
class PlanItem:
    key: str
    size: int
    section: str
    parts: tuple
    name: str


def safe_part(text, limit=80):
    """One folder name that Windows accepts: no reserved characters or device names, no trailing dot or space."""
    cleaned = INVALID.sub('_', unicodedata.normalize('NFC', str(text))).strip().rstrip('. ')
    cleaned = re.sub(r'\s+', ' ', cleaned)[:limit].rstrip('. ')
    if not cleaned:
        return '_'
    return '_' + cleaned if RESERVED.match(cleaned) else cleaned


def safe_name(name, budget):
    """A file name that fits `budget` characters, keeping its extension."""
    suffix = PurePosixPath(name).suffix[:16]
    stem = safe_part(PurePosixPath(name).stem if suffix else name, limit=200)
    room = max(8, budget - len(suffix))
    return stem[:room].rstrip('. ') + suffix


def _normalized(path):
    text = unicodedata.normalize('NFC', str(path or '')).strip().replace('/', '\\')
    return str(PureWindowsPath(text)).rstrip('\\').casefold()


def destination_problem(destination, source, roots):
    """Reason code why `destination` cannot receive an export of `source`, or None. Checks the text only."""
    text = str(destination or '').strip()
    if text.startswith(('\\\\', '//')):
        return 'destino_unc'
    if not re.match(r'^[A-Za-z]:[\\/]', text):
        return 'destino_no_absoluto'
    if re.search(r'[<>"|?*\x00-\x1f]', text[2:]) or any(part in {'..', '.'} for part in re.split(r'[\\/]', text)):
        return 'destino_invalido'
    target, origin = _normalized(text), _normalized(source)
    if not any(target == _normalized(r) or target.startswith(_normalized(r) + '\\') for r in roots):
        return 'destino_fuera_de_raices'
    if target == origin or target.startswith(origin + '\\'):
        return 'destino_dentro_origen'
    if origin.startswith(target + '\\'):
        return 'origen_dentro_destino'
    return None


def build_plan(entries, maps, include=None, destination_length=0):
    """entries: [(key, size, group)]. maps: placements {path: folders}, later ones win. Returns the plan.

    {'items': [PlanItem], 'excluded': {group: n}, 'omitted': {section: n}}
    """
    include = set(DEFAULT_INCLUDE if include is None else include) & set(SECTIONS)
    placed = {}
    for mapping in maps:
        placed.update(mapping)
    items, excluded, omitted = [], {}, {}
    for key, size, group in entries:
        pure = PurePosixPath(key.replace('\\', '/'))
        if group in NEVER_GROUPS or pure.suffix.lower() in NEVER_EXTENSIONS:
            excluded[group] = excluded.get(group, 0) + 1
            continue
        parts = placed.get(key)
        if parts:
            section = SECTION_BY_LABEL.get(parts[0], GROUP_SECTION.get(group, 'sin_clasificar'))
        else:
            section = GROUP_SECTION.get(group, 'sin_clasificar')
            if section == 'sin_clasificar':
                parts = (SECTIONS[section], *pure.parts[:-1])
            else:
                parts = (SECTIONS[section], 'Otros')
        if section not in include:
            omitted[section] = omitted.get(section, 0) + 1
            continue
        folders = tuple(safe_part(p) for p in parts)
        used = destination_length + sum(len(p) + 1 for p in folders)
        items.append(PlanItem(key, size, section, folders, safe_name(pure.name, max(16, MAX_PATH - used - 1))))
    return {'items': items, 'excluded': excluded, 'omitted': omitted, 'include': sorted(include)}


def preview(plan, destination, free_bytes=None):
    """Counts for the person to confirm before anything is written."""
    sections, collisions, seen = {}, 0, set()
    for item in plan['items']:
        entry = sections.setdefault(item.section, {'files': 0, 'bytes': 0, 'folders': set(), 'sample': []})
        entry['files'] += 1
        entry['bytes'] += item.size
        entry['folders'].add(item.parts)
        if len(entry['sample']) < 3:
            entry['sample'].append('/'.join((*item.parts, item.name)))
        path = '/'.join((*item.parts, item.name)).casefold()
        collisions += path in seen
        seen.add(path)
    total_bytes = sum(e['bytes'] for e in sections.values())
    return {
        'mode': 'preview',
        'destination': str(destination),
        'total': len(plan['items']),
        'bytes': total_bytes,
        'free_bytes': free_bytes,
        'enough_space': None if free_bytes is None else free_bytes > total_bytes * 1.05,
        'collisions': collisions,
        'sections': {
            key: {'files': e['files'], 'bytes': e['bytes'], 'folders': len(e['folders']), 'sample': e['sample']}
            for key, e in sections.items()
        },
        'excluded': plan['excluded'],
        'omitted': plan['omitted'],
        'include': plan['include'],
    }


def manifest_text(records):
    """CSV of what was copied (estado, sección, ruta virtual, ruta original, SHA-256, bytes, motivo)."""
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(['estado', 'seccion', 'ruta_virtual', 'ruta_original', 'sha256', 'bytes', 'motivo'])
    for r in records:
        # A cell that starts with = + - @ would run as a formula when the CSV is opened in Excel.
        writer.writerow([("'" + str(v)) if str(v).startswith(('=', '+', '-', '@')) else v for v in r])
    return out.getvalue()
