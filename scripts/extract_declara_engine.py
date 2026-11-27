"""Extrae la lógica original sin cargar Tk, Firefox ni configuración de escritorio.

Sobre el código original sólo se aplican los parches de ``PATCHES`` (rediseño de Declara aprobado el 26/11/2026,
sección 3). Cada parche debe aparecer exactamente una vez; la prueba de paridad aplica la misma lista al original y
exige que el resultado coincida con el motor extraído. La lógica nueva que no modifica funciones originales vive en
``backend/app/declara_rules.py``.
"""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'reference/desktop/Declara/organizador_sat_v26.py'
TARGET = ROOT / 'backend/app/declara_engine.py'
CORE = {
    'PdfInfo',
    'strip_accents',
    'norm',
    'sanitize_company_name',
    'add_duplicate_suffix',
    '_existing_copy_index',
    'sha256_file',
    'first_page_text',
    'all_pages_text',
    '_find',
    'parse_pdf',
    'analyze_folder',
    'rfc_company_start_date',
    'compute_month_completeness',
    'execute_renames',
}

# Parches aprobados (función -> [(texto original, texto nuevo)]).
PATCHES = {
    # 3.1 y 3.5: huella de copia idéntica, conteo en el control mensual y origen del nombre (manual o motor).
    'PdfInfo': [
        (
            '    manual_override: bool = False\n',
            '    manual_override: bool = False\n'
            '    identical_to: Optional[str] = None\n'
            '    count_in_control: bool = True\n'
            '    origin: str = ""\n',
        )
    ],
    'parse_pdf': [
        # 3.7: PDF escaneado.
        (
            '        info.detail = "La primera página no contiene texto extraíble."\n',
            '        info.detail = "El PDF es una imagen, sin texto: clasifícalo manualmente."\n',
        ),
        # 3.2: el consecutivo de complementaria nunca toma el año.
        (
            '        seq = re.search(r"(?:COMPLEMENTARIA|COMPL|COMP)[ _.-]*(?:\\(|\\[)?(\\d+)(?:\\)|\\])?\\s*$", name_text)\n'
            '        if not seq:\n'
            '            seq = re.search(r"(?:\\(|\\[)?(\\d+)(?:\\)|\\])?\\s*$", name_text)\n',
            '        # Sólo 1 o 2 dígitos tras COMPL/COMPLEMENTARIA o entre paréntesis o corchetes: nunca un año.\n'
            '        # El consecutivo final de un nombre que ya sigue el estándar (N.k.-) se conserva.\n'
            '        seq = re.search(r"(?:COMPLEMENTARIA|COMPL|COMP)[ _.-]*(?:\\(|\\[)?(\\d{1,2})(?:\\)|\\])?\\s*$", name_text)\n'
            '        if not seq:\n'
            '            seq = re.search(r"(?:\\(|\\[)(\\d{1,2})(?:\\)|\\])\\s*$", name_text)\n'
            '        if not seq and re.match(r"^\\d{1,2}\\.\\d+(?:\\.\\d+)?\\.-\\s", name_text):\n'
            '            seq = re.search(r"\\s(\\d{1,2})\\s*$", name_text)\n',
        ),
    ],
    'analyze_folder': [
        # 3.6: RFC contra la empresa seleccionada.
        (
            'def analyze_folder(folder: Path, company: str) -> list[PdfInfo]:\n',
            'def analyze_folder(folder: Path, company: str, expected_rfc: Optional[str] = None) -> list[PdfInfo]:\n',
        ),
        # 3.1: copias idénticas por huella; el primero (orden del resolvedor de colisiones) se procesa.
        (
            '    infos = [parse_pdf(p, company) for p in pdfs]\n',
            '    infos = [parse_pdf(p, company) for p in pdfs]\n'
            '\n'
            '    # Copias idénticas por huella SHA-256: el primero según el orden del resolvedor de colisiones se\n'
            '    # procesa; los demás no se renombran, no reciben consecutivo y no cuentan en el control mensual.\n'
            '    by_hash: dict[str, list[PdfInfo]] = defaultdict(list)\n'
            '    for i in infos:\n'
            '        try:\n'
            '            i.sha256 = sha256_file(i.path)\n'
            '        except Exception:\n'
            '            continue\n'
            '        by_hash[i.sha256].append(i)\n'
            '    for same in by_hash.values():\n'
            '        if len(same) <= 1:\n'
            '            continue\n'
            '        same.sort(key=lambda i: (\n'
            '            _existing_copy_index(i.path.name, i.expected_name) if i.expected_name else 999999,\n'
            '            0 if i.status == "CORRECTO" else 1,\n'
            '            i.operation or "",\n'
            '            i.path.name.casefold(),\n'
            '        ))\n'
            '        for i in same[1:]:\n'
            '            i.status = "COPIA IDÉNTICA"\n'
            '            i.identical_to = same[0].path.name\n'
            '            i.detail = f"Igual a {same[0].path.name}"\n',
        ),
        (
            '    primary_rfc = Counter(rfcs).most_common(1)[0][0] if rfcs else None\n',
            '    primary_rfc = (expected_rfc or "").strip().upper() or (Counter(rfcs).most_common(1)[0][0] if rfcs else None)\n',
        ),
        (
            '                i.detail = f"RFC {i.rfc}; el RFC principal detectado es {primary_rfc}."\n',
            '                i.detail = (\n'
            '                    f"RFC {i.rfc}; el RFC de la empresa es {primary_rfc}." if expected_rfc\n'
            '                    else f"RFC {i.rfc}; el RFC principal detectado es {primary_rfc}."\n'
            '                )\n',
        ),
    ],
}


def apply_patches(name, segment):
    """The segment with its approved patches. Each one must match exactly once, or the extraction stops."""
    for old, new in PATCHES.get(name, []):
        if segment.count(old) != 1:
            raise ValueError(f'El parche de {name} no coincide exactamente una vez: {old[:60]!r}')
        segment = segment.replace(old, new)
    return segment


def node_source(source, node):
    """Source of a top-level node, decorators included."""
    start = min([node.lineno] + [d.lineno for d in node.decorator_list])
    return '\n'.join(source.splitlines()[start - 1 : node.end_lineno])


def extract(patched=True):
    """The engine module's source. `patched=False` gives the untouched original (used by the parity tests)."""
    source = SOURCE.read_text(encoding='utf-8-sig')
    tree = ast.parse(source)
    sections = [
        '"""Motor extraído de Declara v0.2.6 con los parches aprobados. Regenerar con scripts/extract_declara_engine.py."""',
        'from __future__ import annotations\nimport hashlib\nimport os\nimport re\nimport tempfile\nimport unicodedata\nfrom collections import Counter, defaultdict\nfrom dataclasses import dataclass\nfrom datetime import date\nfrom pathlib import Path\nfrom typing import Optional\nfrom pypdf import PdfReader\nPYPDF_IMPORT_ERROR = None',
    ]
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in CORE:
            segment = node_source(source, node)
            sections.append(apply_patches(node.name, segment) if patched else segment)
        elif isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id in {'MONTHS', 'MONTH_NUMBERS', 'INVALID_FILENAME_CHARS'}
            for t in node.targets
        ):
            sections.append(ast.get_source_segment(source, node))
        elif isinstance(node, ast.ClassDef) and node.name == 'App':
            for method in node.body:
                if isinstance(method, ast.FunctionDef) and method.name in {
                    '_next_duplicate_name',
                    '_manual_name_for_type',
                }:
                    # Sólo sustituye dependencias de widgets por argumentos explícitos.
                    segment = ast.get_source_segment(source, method)
                    lines = segment.splitlines()
                    lines = [lines[0]] + [line[4:] if line.startswith('    ') else line for line in lines[1:]]
                    segment = (
                        '\n'.join(lines).replace('self.infos', 'infos').replace('self.company_var.get()', 'company')
                    )
                    segment = segment.replace(
                        '_next_duplicate_name(self, info: PdfInfo)',
                        'next_duplicate_name(info: PdfInfo, infos: list[PdfInfo])',
                    )
                    segment = segment.replace(
                        '_manual_name_for_type(self, info: PdfInfo, choice: str)',
                        'manual_name_for_type(info: PdfInfo, choice: str, infos: list[PdfInfo], company: str)',
                    )
                    sections.append(segment)
    return '\n\n\n'.join(sections) + '\n'


if __name__ == '__main__':
    TARGET.write_text(extract(), encoding='utf-8')
