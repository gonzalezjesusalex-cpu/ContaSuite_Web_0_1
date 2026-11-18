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
    'nomina': ('Nómina y trabajadores', False),
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
    in_credentials = any(re.search(r'FIEL|E-?FIRMA|SELLO|\bCSD\b', f) for f in folders)

    if re.search(r'CONTRASE|PASSWORD|CONTRA_\d', name) or (in_credentials and ext in {'.txt', '.doc', '.docx'}):
        return 'contrasenas', None
    if ext in CREDENTIAL_EXTENSIONS or (ext in {'.zip', '.rar', '.7z'} and (in_credentials or re.search(r'FIEL|E-?FIRMA|CSD|SELLO', name))):
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

    if ext in {'.sua', '.log'} or re.search(r'IDSE|SIPARE|\bEMA\b|\bEBA\b|_EMA_|_EBA_|CEDULA|CONFRONTA|LIQUIDACION|DIFERENCIAS', name):
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
    if re.search(r'ACTA|\bRPC\b|CONSTANCIA|(?<![A-Z0-9])CSF(?![A-Z0-9])|REPSE|REGISTRO|\bTIP\b|PODER|CONTRATO', name + ' ' + where):
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
