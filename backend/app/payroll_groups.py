"""Nómina por quincena (XML + recibo PDF) y expedientes de trabajadores.

Metadata only. A payroll XML (CFDI tipo N) and its recibo PDF are paired when they share the same file name in the same
folder; each quincena reports what is unpaired. Worker folders list which essential documents each person has. No file
is opened and nothing here is a fiscal or labor conclusion.
"""

import re
from collections import defaultdict
from pathlib import PurePosixPath

from .folder_groups import MONTHS, fold

QUINCENAL = re.compile(r'QUINCENAL_(20\d{2})_(\d{1,3})_(\d{3})', re.I)
WORKER_DOCS = (
    ('alta', 'Alta IMSS', r'ALTA IMSS'),
    ('nss', 'Número de seguridad social', r'SEGURIDAD SOCIAL|(?<![A-Z0-9])NSS(?![A-Z0-9])|TARJETANSS'),
    ('curp', 'CURP', r'CURP'),
    ('ine', 'INE', r'(?<![A-Z0-9])INE(?![A-Z0-9])'),
    ('csf', 'Constancia fiscal (CSF / CIF)', r'(?<![A-Z0-9])(CSF|CIF)(?![A-Z0-9])'),
    ('domicilio', 'Comprobante de domicilio', r'DOMICILIO'),
    ('idse', 'Lote IDSE / recibo del IMSS', r'IDSE|RECIBO'),
    ('combinado', 'Documentos reunidos en un solo archivo', r'^DOCUMENTOS\b'),
)
WORKER_LABELS = {key: label for key, label, _ in WORKER_DOCS} | {'otro': 'Otro'}
WORKER_REQUIRED = ('alta', 'nss', 'ine', 'csf')
WORKER_FOLDER = re.compile(r'^(TRABAJADOR(ES)?|DOCUMENTOS DEL TRABAJADOR.*)$')


def quincena_label(number):
    month = (number + 1) // 2
    return f'{"1.ª" if number % 2 else "2.ª"} quincena de {MONTHS[month - 1].capitalize()}' if 1 <= month <= 12 else str(number)


class PayrollIndex:
    def __init__(self):
        self.xml, self.pdf = {}, []

    @staticmethod
    def _stem(path):
        norm = path.replace('\\', '/')
        return PurePosixPath(norm).with_suffix('').as_posix().casefold()

    def add_xml(self, path):
        self.xml[self._stem(path)] = path

    def add_pdf(self, path):
        self.pdf.append(path)

    def virtual(self):
        """{path: folders} for every payroll XML and recibo: Nómina / year / «13.- 1ERA QNA JULIO»."""
        out = {}
        for path in [*self.xml.values(), *self.pdf]:
            found = QUINCENAL.search(PurePosixPath(path.replace('\\', '/')).name)
            if found:
                year, number = int(found.group(1)), int(found.group(2))
                month = (number + 1) // 2
                label = f'{number}.- {"1ERA" if number % 2 else "2DA"} QNA {MONTHS[month - 1] if 1 <= month <= 12 else ""}'
                out[path] = ('Nómina', str(year), label.strip())
        return out

    def result(self):
        quincenas = defaultdict(lambda: {'xml': [], 'pdf': [], 'paired': 0})
        pdf_stems = set()
        for path in self.pdf:
            found = QUINCENAL.search(PurePosixPath(path.replace('\\', '/')).name)
            if not found:
                continue
            key = (int(found.group(1)), int(found.group(2)))
            quincenas[key]['pdf'].append(path)
            pdf_stems.add(self._stem(path))
        for stem, path in self.xml.items():
            found = QUINCENAL.search(PurePosixPath(path.replace('\\', '/')).name)
            if not found:
                continue
            key = (int(found.group(1)), int(found.group(2)))
            quincenas[key]['xml'].append(path)
            if stem in pdf_stems:
                quincenas[key]['paired'] += 1
        rows = []
        for (year, number), q in sorted(quincenas.items()):
            sin_pdf = len(q['xml']) - q['paired']
            sin_xml = len(q['pdf']) - q['paired']
            rows.append(
                {
                    'y': year,
                    'q': number,
                    'label': quincena_label(number),
                    'xml': len(q['xml']),
                    'pdf': len(q['pdf']),
                    'paired': q['paired'],
                    'sin_pdf': sin_pdf,
                    'sin_xml': sin_xml,
                    's': 'completo' if not sin_pdf and not sin_xml else 'faltante',
                    'files': sorted(q['xml'] + q['pdf'])[:40],
                }
            )
        numbers = [r['q'] for r in rows]
        gaps = [n for n in range(min(numbers), max(numbers) + 1) if n not in numbers] if numbers else []
        return {
            'quincenas': rows,
            'huecos': gaps,
            'completas': sum(1 for r in rows if r['s'] == 'completo'),
            'faltantes': sum(1 for r in rows if r['s'] == 'faltante'),
            'total': sum(r['xml'] + r['pdf'] for r in rows),
        }


def worker_doc(name):
    folded = fold(name)
    for key, _, pattern in WORKER_DOCS:
        if re.search(pattern, folded):
            return key
    return 'otro'


class WorkersIndex:
    """Documents per worker folder («TRABAJADOR/01.- NOMBRE/…»). Personal data: names and counts only."""

    def __init__(self):
        self.workers = defaultdict(list)

    def add(self, path):
        parts = path.replace('\\', '/').split('/')
        who = ''
        for n, part in enumerate(parts[:-1]):
            if WORKER_FOLDER.match(fold(part).strip()):
                if n + 1 < len(parts) - 1:
                    who = parts[n + 1]
                break
        who = re.sub(r'^\d{1,2}\s*(?:\.-?)?\s*', '', who).strip()
        self.workers[who].append({'p': path, 't': worker_doc(parts[-1])})

    def virtual(self):
        """{path: folders}: Trabajadores / person. Personal data: the export leaves it out unless asked."""
        return {
            item['p']: ('Trabajadores', who or 'Sin carpeta individual')
            for who, items in self.workers.items()
            for item in items
        }

    def result(self):
        rows = []
        for who, items in sorted(self.workers.items()):
            have = {i['t'] for i in items}
            rows.append(
                {
                    'w': who,
                    'files': items[:30],
                    'count': len(items),
                    # A single combined PDF stands for the whole set; the content is not checked.
                    'faltan': [k for k in WORKER_REQUIRED if k not in have] if who and 'combinado' not in have else [],
                }
            )
        return {
            'workers': rows,
            'total': sum(r['count'] for r in rows),
            'personas': sum(1 for r in rows if r['w']),
            'incompletos': sum(1 for r in rows if r['faltan']),
        }
