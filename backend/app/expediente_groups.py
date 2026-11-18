"""Expediente de la empresa: constitutivos, CSF, REPSE, registro patronal e identificación del representante.

Metadata only (names and folders). It lists which essential documents exist and which are missing, and flags a CSF
whose file name carries another company's RFC. It does not validate the content of any document.
"""

import re
from pathlib import PurePosixPath

from .folder_groups import fold

# Order matters: the first match wins («04.-RPC ACTA ASAMBLEA» is an RPC document).
DOCS = (
    ('rpc', 'Registro público de comercio (RPC)', r'\bRPC\b'),
    ('repse', 'REPSE', r'REPSE'),
    ('patronal', 'Registro o tarjeta patronal', r'REGISTRO PATRONAL|TARJETA PATRONAL|(?<![A-Z0-9])TIP(?![A-Z0-9])'),
    ('csf', 'Constancia de situación fiscal', r'(?<![A-Z0-9])CSF(?![A-Z0-9])|CONSTANCIA'),
    ('objeto', 'Objeto social', r'OBJETO SOCIAL'),
    ('ine', 'Identificación (INE / CURP)', r'(?<![A-Z0-9])INE(?![A-Z0-9])|CURP'),
    ('domicilio', 'Comprobante de domicilio', r'TELMEX|\bCFE\b|DOMICILIO'),
    ('nomina_muestra', 'Recibo de nómina de muestra', r'RECIBO DE NOMINA'),
    ('acta', 'Acta constitutiva o de asamblea', r'ACTA(?!\s*(DE\s*)?NACIMIENTO)|PROTOCOLIZADA'),
)
LABELS = {key: label for key, label, _ in DOCS} | {'otro': 'Otro documento'}
# The essentials of a company's file.
REQUIRED = ('acta', 'rpc', 'csf', 'patronal', 'ine')
RFC_IN_NAME = re.compile(r'(?<![A-Z0-9Ñ&])([A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3})(?![A-Z0-9])')
PERSON_FOLDER = re.compile(r'\d{1,2}\s*\.-')  # «01.- NOMBRE»: documents of one person, not of the company
REASONS = {'rfc_ajeno': 'El RFC del nombre del archivo no es el de esta empresa.'}


def doc_type(path):
    name = fold(PurePosixPath(path.replace('\\', '/')).name)
    for key, _, pattern in DOCS:
        if re.search(pattern, name):
            return key
    return 'otro'


class ExpedienteIndex:
    def __init__(self, rfc=''):
        self.rfc = ''.join((rfc or '').split()).upper()
        self.items = []

    def add(self, path):
        norm = path.replace('\\', '/')
        parts = norm.split('/')
        kind = doc_type(norm)
        why = ''
        owner = parts[0] if len(parts) > 1 else ''
        if kind == 'csf' and self.rfc and not PERSON_FOLDER.match(owner):
            found = RFC_IN_NAME.search(fold(parts[-1]))
            if found and found.group(1) != self.rfc:
                why = 'rfc_ajeno'
        self.items.append(
            {
                'p': path,
                't': kind,
                'o': owner,
                's': 'revisar' if why else 'ok',
                'why': why,
            }
        )

    def virtual(self):
        """{path: folders}: Expediente de la empresa / document type (a person's folder goes under Personas)."""
        out = {}
        for i in self.items:
            if PERSON_FOLDER.match(i['o']):
                person = re.sub(r'^\d{1,2}\s*\.-?\s*', '', i['o']).strip() or i['o']
                out[i['p']] = ('Expediente de la empresa', 'Personas', person)
            else:
                out[i['p']] = ('Expediente de la empresa', LABELS.get(i['t'], 'Otro documento'))
        return out

    def result(self):
        # Only company-level documents count toward the checklist: a person's folder is not the company's file.
        company = [i for i in self.items if i['s'] == 'ok' and not PERSON_FOLDER.match(i['o'])]
        have = {i['t'] for i in company}
        return {
            'rows': self.items[:600],
            'total': len(self.items),
            'faltan': [k for k in REQUIRED if k not in have],
            'revisar': sum(1 for i in self.items if i['s'] == 'revisar'),
        }
