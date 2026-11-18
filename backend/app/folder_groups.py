"""Folder analysis: classify every file of a company folder into document groups (metadata only).

Pure functions, no I/O: the local agent feeds them relative paths, sizes and (for XML) the first bytes of the file.
Sensitive groups (e.firma/CSD material and password notes) are reported as counts only: names are never returned.
Classification is by extension, folder names and file names; it is a proposal for review, never a fiscal conclusion.
"""

import re
import unicodedata
from collections import defaultdict
from pathlib import PurePosixPath

# key -> (label, sensitive). Order is the display order.
GROUPS = {
    'cfdi_xml': ('CFDI (XML)', False),
    'cfdi_pdf': ('Representaciones PDF de CFDI', False),
    'sat_reportes': ('Reportes del SAT (Emitidos / Recibidos)', False),
    'impuestos': ('Declaraciones, acuses y pagos', False),
    'imss': ('IMSS, SUA e IDSE', False),
    'nomina': ('Nómina (recibos y quincenas)', False),
    'trabajadores': ('Expedientes de trabajadores (datos personales)', False),
    'estados_financieros': ('Estados financieros', False),
    'legal': ('Constitutivos, constancias y REPSE', False),
    'identificaciones': ('Identificaciones', False),
    'credenciales': ('e.firma y sello digital (sólo conteo)', True),
    'contrasenas': ('Notas de contraseñas (sólo conteo)', True),
    'ruido': ('Archivos de sistema o accesos directos', False),
    'otros': ('Otros', False),
}
CFDI_TIPOS = {'I': 'Ingreso', 'E': 'Egreso', 'P': 'Pago', 'N': 'Nómina', 'T': 'Traslado'}
CREDENTIAL_EXTENSIONS = {'.key', '.cer', '.req', '.sdg', '.pfx', '.p12', '.pem', '.ren'}
NOISE_NAMES = {'thumbs.db', 'desktop.ini', '.ds_store'}
NOISE_EXTENSIONS = {'.lnk', '.tmp', '.bak'}
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.heic', '.tif', '.tiff', '.webp'}
UUID_NAME = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', re.I)
SAT_REPORT = re.compile(r'^(emitid|recibid)[a-z]*-[a-z0-9&]{12,13}-\d{6}', re.I)
SAT_ENTITY = re.compile(r'<(?:\w+:)?Comprobante\b[^>]*', re.S)


def fold(text):
    """Upper-case without accents; tolerant of the mojibake some Windows names carry."""
    return ''.join(c for c in unicodedata.normalize('NFKD', text.upper()) if not unicodedata.combining(c))


def classify(relative_path, size=0, tipo=None):
    """Return (group, subgroup or None) for one file. `tipo` is the CFDI TipoDeComprobante when already known."""
    path = PurePosixPath(relative_path.replace('\\', '/'))
    name = fold(path.name)
    ext = path.suffix.lower()
    folders = [fold(p) for p in path.parts[:-1]]
    where = ' / '.join(folders)
    in_credentials = any(re.search(r'FIEL|E-?FIRMA|SELLO|\bCSD\b|CERTIFICADO', f) for f in folders)

    if re.search(r'CONTRASE|PASSWORD|CONTRA_\d|\bUSUARIO\b|^ACCESOS?\b', name) or (in_credentials and ext in {'.txt', '.doc', '.docx'}):
        return 'contrasenas', None
    if ext in CREDENTIAL_EXTENSIONS or (ext == '.pdf' and in_credentials) or (ext in {'.zip', '.rar', '.7z'} and (in_credentials or re.search(r'FIEL|E-?FIRMA|\bCSD\b|SELLO', name))):
        return 'credenciales', None
    if name.lower() in NOISE_NAMES or ext in NOISE_EXTENSIONS or name.startswith('~$'):
        return 'ruido', None

    if ext == '.xml':
        if tipo is None:
            return 'cfdi_xml', None
        return 'cfdi_xml', CFDI_TIPOS.get(tipo, 'Otro tipo') if tipo else 'XML que no es CFDI'
    if ext == '.pdf' and UUID_NAME.match(path.name):
        return 'cfdi_pdf', None
    if ext in {'.xls', '.xlsx', '.csv'} and SAT_REPORT.match(path.name):
        return 'sat_reportes', None

    if re.search(r'(^| / )(TRABAJADOR(ES)?|DOCUMENTOS DEL TRABAJADOR[^/]*)( / |$)', where) or re.match(r'TRABAJADOR(ES)?\b', name):
        return 'trabajadores', None
    if (
        ext in {'.sua', '.log'}
        or re.search(r'IDSE|SIPARE|SIAPRE|\bEMA\b|\bEBA\b|_EMA_|_EBA_|CEDULA|CONFRONTA|CONSFRONTA|LIQUIDACION|DIFERENCIAS', name)
        or re.search(r'(^| / )(IMSS|EMISIONES IMSS)( / |$)', where)  # everything filed in the IMSS folders
    ):
        return 'imss', None
    if re.fullmatch(r'(AFIL|ASEG|MOVT)\.TXT', name):
        return 'imss', None
    if re.search(r'DECLARACI|ACUSE|LINEA DE CAPTURA|PAGO|\bISN\b|BIMESTRE|OPINION|\bDEC\d', name) or re.search(
        r'IMPUESTOS|FEDERALES|ESTATALES', where
    ):
        return 'impuestos', None
    if re.search(r'ESTADOS? FINANCIERO|BALANZA|DETALLEMENSUAL', name + ' ' + where):
        return 'estados_financieros', None
    if re.search(r'\bINE\b|CURP|PASAPORTE|IDENTIFICACION|WHATSAPP IMAGE', name):
        return 'identificaciones', None
    if re.search(r'ACTA|\bRPC\b|CONSTANCIA|(?<![A-Z0-9])CSF(?![A-Z0-9])|REPSE|REGISTRO|\bTIP\b|PODER|CONTRATO|TARJETA PATRONAL|OBJETO SOCIAL|TELMEX|\bCFE\b', name + ' ' + where):
        return 'legal', None
    if re.search(r'NOMINA|TRABAJADOR|RECIBO|FINIQUITO', name + ' ' + where):
        return 'nomina', None
    if ext in IMAGE_EXTENSIONS:
        return 'otros', 'Imágenes'
    if ext in {'.zip', '.rar', '.7z'}:
        return 'otros', 'Comprimidos'
    return 'otros', None


def cfdi_tipo(head):
    """TipoDeComprobante of a CFDI from the first bytes of an XML; '' if it is XML but not a CFDI, None if unknown."""
    text = head.decode('utf-8', errors='ignore') if isinstance(head, (bytes, bytearray)) else str(head)
    match = SAT_ENTITY.search(text)
    if not match or 'sat.gob.mx/cfd' not in text:
        return ''
    tipo = re.search(r'TipoDeComprobante\s*=\s*"(\w)"', match.group(0), re.I)
    return tipo.group(1).upper() if tipo else None


MONTHS = ('ENERO', 'FEBRERO', 'MARZO', 'ABRIL', 'MAYO', 'JUNIO', 'JULIO', 'AGOSTO', 'SEPTIEMBRE', 'OCTUBRE', 'NOVIEMBRE', 'DICIEMBRE')
MONTH_NAME = re.compile(r'(' + '|'.join(MONTHS) + r')')
KIND_FOLDER = re.compile(r'^(EMITID|RECIBID)[OA]S?$')
REASONS = {
    'mes_distinto': 'El mes de la carpeta no coincide con la fecha del XML.',
    'tipo_distinto': 'La carpeta (emitidos/recibidos) no coincide con los RFC del XML.',
    'rfc_ajeno': 'Ni el emisor ni el receptor son el RFC de la empresa.',
    'rfc_ambiguo': 'El emisor y el receptor son el RFC de la empresa.',
    'sin_ubicacion': 'No se pudo determinar el mes o si es emitido/recibido.',
    'xml_ilegible': 'No se pudo leer el encabezado del XML.',
}


def month_of_folder(name):
    """(year or None, month) from folder names such as '07.- JULIO', '09- SEPTIEMBRE', '1.- ENERO', '2026-01'."""
    text = fold(name).strip()
    iso = re.fullmatch(r'(20\d{2})[-_ ](0[1-9]|1[0-2])', text)
    if iso:
        return int(iso.group(1)), int(iso.group(2))
    named = MONTH_NAME.search(text)
    if not named:
        return None, None
    month = MONTHS.index(named.group(1)) + 1
    number = re.match(r'\s*(\d{1,2})\s*[.\-)]', text)
    if number and int(number.group(1)) != month:
        return None, None  # the number and the name disagree: not trusted
    return None, month


def folder_context(relative_path):
    """Year, month and kind ('E'/'R') suggested by the folders of a path, nearest folder first; None when absent."""
    year = month = kind = None
    for part in reversed(PurePosixPath(relative_path.replace('\\', '/')).parts[:-1]):
        folded = fold(part).strip()
        if kind is None and KIND_FOLDER.match(folded):
            kind = 'E' if folded.startswith('EMITID') else 'R'
        if year is None:
            found = re.search(r'EJERCICIO\s*(20\d{2})', folded)
            year = int(found.group(1)) if found else None
        if month is None:
            y, m = month_of_folder(part)
            month = m
            year = year or y
    return year, month, kind


def cfdi_info(head):
    """Fecha (YYYY-MM), tipo, emisor and receptor RFC from the first bytes of a CFDI; None when it is not one."""
    text = head.decode('utf-8', errors='ignore') if isinstance(head, (bytes, bytearray)) else str(head)
    root = SAT_ENTITY.search(text)
    if not root or 'sat.gob.mx/cfd' not in text:
        return None
    attrs = root.group(0)
    date = re.search(r'\bFecha\s*=\s*"(\d{4})-(\d{2})-\d{2}', attrs)
    tipo = re.search(r'TipoDeComprobante\s*=\s*"(\w)"', attrs, re.I)
    side = lambda tag: (  # noqa: E731
        lambda m: m.group(1).upper() if m else ''
    )(re.search(r'<(?:\w+:)?' + tag + r'\b[^>]*?\bRfc\s*=\s*"([^"]+)"', text, re.S))
    return {
        'month': (int(date.group(1)), int(date.group(2))) if date else None,
        'tipo': tipo.group(1).upper() if tipo else '',
        'emisor': side('Emisor'),
        'receptor': side('Receptor'),
    }


def place_cfdi(relative_path, info, rfc):
    """Virtual place of one CFDI XML: evidence of the XML first, the folders as a cross-check.

    Returns {'y', 'm', 'k', 's' (ok|revisar), 'why', 'src'}. Nothing here changes a file.
    """
    year, month, kind = folder_context(relative_path)
    own = ''.join((rfc or '').split()).upper()
    if info is None:
        return {'y': year, 'm': month, 'k': kind, 's': 'revisar', 'why': 'xml_ilegible', 'src': 'carpeta'}
    xml_month = info['month']
    role = None
    if own:
        issuer, receiver = info['emisor'] == own, info['receptor'] == own
        role = 'E' if issuer and not receiver else 'R' if receiver and not issuer else None
        why = 'rfc_ambiguo' if issuer and receiver else 'rfc_ajeno' if not issuer and not receiver else ''
    else:
        why = ''
    y, m = (xml_month if xml_month else (year, month))
    k = role or kind
    if not why:
        if xml_month and month and xml_month[1] != month or (xml_month and year and xml_month[0] != year):
            why = 'mes_distinto'
        elif role and kind and role != kind:
            why = 'tipo_distinto'
        elif not (m and k):
            why = 'sin_ubicacion'
    return {'y': y, 'm': m, 'k': k, 's': 'revisar' if why else 'ok', 'why': why, 'src': 'xml' if xml_month else 'carpeta'}


class Summary:
    """Accumulates classified files without keeping them all in memory beyond a few examples per group."""

    def __init__(self, examples=6):
        self.examples = examples
        self.total = 0
        self.bytes = 0
        self.rows = defaultdict(lambda: {'count': 0, 'bytes': 0, 'extensions': defaultdict(int), 'subgroups': defaultdict(int), 'examples': []})
        self.extensions = defaultdict(int)

    def add(self, relative_path, size, tipo=None):
        group, sub = classify(relative_path, size, tipo)
        ext = PurePosixPath(relative_path).suffix.lower() or '(sin extensión)'
        row = self.rows[group]
        row['count'] += 1
        row['bytes'] += size
        row['extensions'][ext] += 1
        if sub:
            row['subgroups'][sub] += 1
        if not GROUPS[group][1] and len(row['examples']) < self.examples:
            row['examples'].append(relative_path)
        self.total += 1
        self.bytes += size
        self.extensions[ext] += 1
        return group

    def result(self):
        groups = []
        for key, (label, sensitive) in GROUPS.items():
            row = self.rows.get(key)
            if not row:
                continue
            groups.append(
                {
                    'key': key,
                    'label': label,
                    'sensitive': sensitive,
                    'count': row['count'],
                    'bytes': row['bytes'],
                    'extensions': dict(sorted(row['extensions'].items(), key=lambda kv: -kv[1])),
                    'subgroups': dict(sorted(row['subgroups'].items(), key=lambda kv: -kv[1])),
                    'examples': row['examples'],
                }
            )
        return {
            'total': self.total,
            'bytes': self.bytes,
            'groups': groups,
            'extensions': dict(sorted(self.extensions.items(), key=lambda kv: -kv[1])[:40]),
        }


MAX_CFDI_ROWS = 6000
REPORT_NAME = re.compile(r'^(emitid|recibid)[a-z]*-[a-z0-9&]{12,13}-(20\d{2})(0[1-9]|1[0-2])', re.I)


class CfdiIndex:
    """Virtual placement of every CFDI file: XML (by its own content), PDF (inherits its XML's place when the file name
    is the same in the same folder; otherwise the folders decide) and SAT reports (by their name). Metadata only.
    """

    def __init__(self, rfc=''):
        self.rfc = rfc
        self.xml, self.pdf, self.reports, self.dropped = {}, [], [], 0

    def add_xml(self, path, info):
        place = place_cfdi(path, info, self.rfc)
        place['t'] = (info or {}).get('tipo', '')
        self.xml[PurePosixPath(path).with_suffix('').as_posix().casefold()] = (path, place)

    def add_pdf(self, path):
        self.pdf.append(path)

    def add_report(self, path):
        match = REPORT_NAME.match(PurePosixPath(path).name)
        if match:
            kind = 'E' if match.group(1).lower() == 'emitid' else 'R'
            self.reports.append((path, int(match.group(2)), int(match.group(3)), kind))

    def result(self):
        rows = [dict(p=path, g='xml', **place) for path, place in self.xml.values()]
        for path in self.pdf:
            twin = self.xml.get(PurePosixPath(path).with_suffix('').as_posix().casefold())
            if twin:
                place = {k: v for k, v in twin[1].items() if k != 'src'}
                rows.append(dict(p=path, g='pdf', src='xml', **place))
                continue
            year, month, kind = folder_context(path)
            why = '' if month and kind else 'sin_ubicacion'
            rows.append(dict(p=path, g='pdf', y=year, m=month, k=kind, t='', s='revisar' if why else 'ok', why=why, src='carpeta'))
        for path, year, month, kind in self.reports:
            rows.append(dict(p=path, g='reporte', y=year, m=month, k=kind, t='', s='ok', why='', src='nombre'))
        self.dropped = max(0, len(rows) - MAX_CFDI_ROWS)
        counts = defaultdict(int)
        for row in rows:
            counts[row['s']] += 1
        return {'rows': rows[:MAX_CFDI_ROWS], 'total': len(rows), 'ok': counts['ok'], 'revisar': counts['revisar'], 'dropped': self.dropped}
