"""Declaraciones y acuses: pairs each declaration with its acuse using only file names and folders.

It proposes pairs and flags what is missing; it never merges, moves or accredits compliance (metadata only).
Pairing happens inside one folder, scope (federal / estatal / anual), period and set of qualifiers
(complementaria, RESICO, salarios), in file-number order: «3.-» goes before «3.2.-».
"""

import re
from collections import defaultdict
from pathlib import PurePosixPath

from .folder_groups import MONTH_NAME, MONTHS, folder_context, fold, month_dir

REASONS = {
    'acuse_sin_declaracion': 'Hay acuse, pero no hay una declaración con el mismo periodo y calificativo.',
    'declaracion_sin_acuse': 'Hay declaración, pero falta su acuse.',
    'acuse_adicional': 'Hay más acuses que declaraciones en este periodo.',
    'sin_periodo': 'No se pudo determinar el periodo.',
}
BIMESTRE = re.compile(r'(\d)\s*(?:ER|DO|RO|TO|O|A)?\s*BIMESTRE')
QUALIFIERS = (('COMPL', r'COMPL'), ('RESICO', r'RESICO'), ('SALARIOS', r'SALARIOS'))
MAX_ROWS = 1500


def tax_kind(name):
    """'acuse', 'declaracion' (typos and portal DEC… files included) or 'otro' from a file name."""
    folded = fold(name)
    if 'ACUSE' in folded:
        return 'acuse'
    if re.search(r'DECLARACI|DECLRACION|^DEC\d', folded):
        return 'declaracion'
    return 'otro'


class TaxIndex:
    def __init__(self):
        self.items = []

    def add(self, path):
        pure = PurePosixPath(path.replace('\\', '/'))
        name = fold(pure.name)
        where = fold('/'.join(pure.parts[:-1]))
        year, month, _ = folder_context(path)
        if re.search(r'ESTATAL|\bISN\b|BIMESTRE', name + ' ' + where):
            scope = 'estatal'
        elif 'ANUAL' in name:
            scope = 'anual'
        else:
            scope = 'federal'
        period = None
        if scope == 'estatal':
            found = BIMESTRE.search(name)
            period = int(found.group(1)) if found else None
        elif scope == 'anual':
            found = re.search(r'(?<!\d)(20\d{2}|\d{2})(?!\d)', name)
            if found:
                year = int(found.group(1)) + (2000 if len(found.group(1)) == 2 else 0)
        else:
            named = MONTH_NAME.search(name)
            period = MONTHS.index(named.group(1)) + 1 if named else month
        number = re.match(r'(\d+(?:\.\d+)*)\.?\s*-', name)
        kind = tax_kind(pure.name)
        # A bare «2DO BIMESTRE <empresa>» beside its declaration is the state acuse: inferred from the name, flagged.
        inferred = kind == 'otro' and scope == 'estatal' and period is not None
        self.items.append(
            {
                'p': path,
                'd': 'acuse' if inferred else kind,
                'inf': inferred,
                'a': scope,
                'y': year,
                'n': period,
                'q': [key for key, pattern in QUALIFIERS if re.search(pattern, name)],
                'seq': tuple(int(x) for x in number.group(1).split('.')) if number else (),
                'dir': pure.parent.as_posix().casefold(),
            }
        )

    def virtual(self):
        """{path: folders} for every file: Impuestos / Federales|Estatales|Anuales / year / period."""
        self.result()  # pairing and review flags first
        scopes = {'federal': 'Federales', 'estatal': 'Estatales', 'anual': 'Anuales'}
        out = {}
        for i in self.items:
            top = ('Impuestos', scopes[i['a']])
            if i['why'] == 'sin_periodo':
                out[i['p']] = ('Impuestos', 'Por revisar')
                continue
            year = str(i['y']) if i['y'] else 'Sin ejercicio'
            if i['a'] == 'anual':
                period = 'Declaración anual'
            elif i['n'] is None:
                period = 'Sin periodo'
            else:
                period = f'Bimestre {i["n"]}' if i['a'] == 'estatal' else month_dir(i['n'])
            out[i['p']] = top + (year, period)
        return out

    def result(self):
        groups = defaultdict(list)
        for item in self.items:
            item.update(pair=None, s='ok', why='')
            if item['d'] == 'otro':
                continue
            if item['n'] is None and item['a'] != 'anual':
                item.update(s='revisar', why='sin_periodo')
                continue
            groups[(item['dir'], item['a'], item['y'], item['n'], tuple(item['q']))].append(item)
        for members in groups.values():
            decls = sorted((i for i in members if i['d'] == 'declaracion'), key=lambda i: (i['seq'], i['p']))
            acuses = sorted((i for i in members if i['d'] == 'acuse'), key=lambda i: (i['seq'], i['p']))
            for decl, acuse in zip(decls, acuses):
                decl['pair'], acuse['pair'] = acuse['p'], decl['p']
            for decl in decls[len(acuses) :]:
                decl.update(s='faltante', why='declaracion_sin_acuse')
            for acuse in acuses[len(decls) :]:
                if decls:
                    acuse.update(s='revisar', why='acuse_adicional')
                else:
                    acuse.update(s='faltante', why='acuse_sin_declaracion')
        rows = [{k: v for k, v in i.items() if k not in {'seq', 'dir'}} for i in self.items][:MAX_ROWS]
        return {
            'rows': rows,
            'total': len(self.items),
            'pairs': sum(1 for r in rows if r['d'] == 'declaracion' and r['pair']),
            'faltantes': sum(1 for r in rows if r['s'] == 'faltante'),
            'revisar': sum(1 for r in rows if r['s'] == 'revisar'),
        }
