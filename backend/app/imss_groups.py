"""Paquete mensual del IMSS: SUA, SIPARE, resumen de liquidación, cédulas, confronta y emisiones del IDSE.

Metadata only: component and month come from file names and folders; nothing is opened (the «_Error.log» files are
only noted as present). It proposes the monthly package and lists what is missing; it never accredits payment.
"""

import re
from collections import defaultdict
from pathlib import PurePosixPath

from .folder_groups import folder_context, fold

COMPONENTS = {
    'sua': 'SUA',
    'sipare': 'SIPARE',
    'resumen': 'Resumen de liquidación',
    'cedula': 'Cédula de determinación',
    'cedula_bim': 'Cédula bimestral',
    'confronta': 'Confronta',
    'diferencias': 'Reporte de diferencias',
    'log': 'Log de error del SUA',
    'ema': 'Emisión mensual (EMA)',
    'eba': 'Emisión bimestral (EBA)',
    'excel': 'Emisión en Excel',
    'idse_txt': 'Archivos IDSE (Afil / Aseg / Movt)',
    'otro': 'Otro documento IMSS',
}
MONTHLY = {'sua', 'sipare', 'resumen', 'cedula', 'cedula_bim', 'confronta', 'diferencias', 'log', 'ema', 'eba', 'excel'}
# Needed in every month's package; the bimestral cédula only in even months (RCV is bimonthly).
CORE = ('sua', 'sipare', 'resumen', 'cedula')
REASONS = {
    'mes_distinto': 'El mes del nombre del archivo no coincide con su carpeta.',
    'varios_folios': 'Hay más de un folio del SUA en este mes.',
    'sin_mes': 'No se pudo determinar el mes.',
}
REGISTRO = re.compile(r'(?<![A-Z0-9])P?([A-Z])(\d{9})\d?(?!\d)')
MAX_ROWS = 1500


def component(path):
    """Component key of one IMSS file from its name and folders."""
    pure = PurePosixPath(path.replace('\\', '/'))
    name = fold(pure.name)
    ext = pure.suffix.lower()
    if ext == '.sua':
        return 'sua'
    if name.endswith('_ERROR.LOG'):
        return 'log'
    if re.fullmatch(r'(AFIL|ASEG|MOVT)\.TXT', name):
        return 'idse_txt'
    if re.search(r'SIPARE|SIAPRE', name):
        return 'sipare'
    if re.search(r'RESUMEN LIQUIDACION', name):
        return 'resumen'
    if 'CEDULA' in name:
        return 'cedula_bim' if 'BIM' in name else 'cedula'
    if re.search(r'CONFRONTA|CONSFRONTA', name):
        return 'confronta'
    if 'DIFERENCIAS' in name:
        return 'diferencias'
    if re.search(r'_EBA(_|\.)', name):
        return 'eba'
    if re.search(r'_EMA(_|\.)', name):
        return 'ema'
    if '_EXCEL' in name or (ext in {'.xls', '.xlsx'} and 'EMISIONES' in fold('/'.join(pure.parts[:-1]))):
        return 'excel'
    if ext == '.pdf' and re.fullmatch(r'[A-Z]\d{10}_\d{6}\.PDF', name):
        return 'sipare'  # the SIPARE copy the SUA leaves inside «Folio_…»
    return 'otro'


def month_from_name(path):
    """(year, month) written in the file name itself, or None."""
    name = PurePosixPath(path.replace('\\', '/')).name
    sua = re.match(r'W(\d{2})(\d{2})\d{3}', name, re.I)
    if sua and 1 <= int(sua.group(2)) <= 12:
        return 2000 + int(sua.group(1)), int(sua.group(2))
    folio = re.search(r'_(\d)(\d{2})\d{3}(?:_Error\.log|\.pdf)$', name, re.I)
    if folio and 1 <= int(folio.group(2)) <= 12:
        return 2020 + int(folio.group(1)), int(folio.group(2))
    emission = re.match(r'(20\d{2})(\d{1,2})_P', name)
    if emission and 1 <= int(emission.group(2)) <= 12:
        return int(emission.group(1)), int(emission.group(2))
    return None


class ImssIndex:
    def __init__(self):
        self.items = []
        self.registros = set()

    def add(self, path):
        norm = path.replace('\\', '/')
        year, month, _ = folder_context(norm)
        named = month_from_name(norm)
        comp = component(norm)
        why = ''
        if named:
            if month and named[1] != month:
                why = 'mes_distinto'
            year, month = named
        found = REGISTRO.search(fold(PurePosixPath(norm).name))
        if found:
            self.registros.add(found.group(1) + found.group(2))
        if comp in MONTHLY and not month:
            why = why or 'sin_mes'
        self.items.append(
            {
                'p': path,
                'c': comp,
                'y': year,
                'm': month if comp in MONTHLY or (comp == 'otro' and named) else None,
                'fo': next((s for s in norm.split('/')[:-1] if s.upper().startswith('FOLIO_')), ''),
                's': 'revisar' if why else 'ok',
                'why': why,
            }
        )

    def result(self):
        months = defaultdict(list)
        for item in self.items:
            if item['m']:
                months[(item['y'], item['m'])].append(item)
        summary = []
        for (year, month), items in sorted(months.items(), key=lambda kv: (kv[0][0] or 0, kv[0][1])):
            have = {i['c'] for i in items}
            need = list(CORE) + (['cedula_bim'] if month % 2 == 0 else [])
            missing = [c for c in need if c not in have]
            if not have & {'confronta', 'diferencias'} and not have <= {'ema', 'eba', 'excel', 'otro'}:
                missing.append('confronta')
            folios = {i['fo'] for i in items if i['fo']}
            notes = []
            if len(folios) > 1:
                notes.append('varios_folios')
            for i in items:
                if i['c'] == 'log':
                    notes.append('log_error')
                    break
            emissions = [c for c in ('ema', 'excel') + (('eba',) if month % 2 == 0 else ()) if c not in have]
            if 'varios_folios' in notes or any(i['s'] == 'revisar' for i in items):
                state = 'revisar'
            elif have <= {'ema', 'eba', 'excel', 'otro'}:
                state = 'parcial'  # only IDSE emissions are filed for this month
            else:
                state = 'faltante' if missing else 'completo'
            summary.append(
                {'y': year, 'm': month, 'have': sorted(have), 'faltan': missing, 'sin_emision': emissions, 'notas': notes, 's': state}
            )
        rows = self.items[:MAX_ROWS]
        general = [i for i in self.items if not i['m']]
        return {
            'rows': rows,
            'months': summary,
            'total': len(self.items),
            'generales': len(general),
            'completos': sum(1 for m in summary if m['s'] == 'completo'),
            'faltantes': sum(1 for m in summary if m['s'] == 'faltante'),
            'revisar': sum(1 for m in summary if m['s'] == 'revisar') + sum(1 for i in rows if i['s'] == 'revisar' and not i['m']),
            'registros': len(self.registros),
        }
