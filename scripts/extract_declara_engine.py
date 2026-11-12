"""Extrae la lógica original sin cargar Tk, Firefox ni configuración de escritorio."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'reference/desktop/Declara/organizador_sat_v26.py'
TARGET = ROOT / 'backend/app/declara_engine.py'
CORE = {'PdfInfo', 'strip_accents', 'norm', 'sanitize_company_name', 'add_duplicate_suffix',
        '_existing_copy_index', 'sha256_file', 'first_page_text', 'all_pages_text', '_find',
        'parse_pdf', 'analyze_folder', 'rfc_company_start_date', 'compute_month_completeness',
        'execute_renames'}


def extract():
    source = SOURCE.read_text(encoding='utf-8-sig')
    tree = ast.parse(source)
    sections = ['"""Motor extraído de Declara v0.2.6. Regenerar con scripts/extract_declara_engine.py."""',
                'from __future__ import annotations\nimport hashlib\nimport os\nimport re\nimport tempfile\nimport unicodedata\nfrom collections import Counter, defaultdict\nfrom dataclasses import dataclass\nfrom datetime import date\nfrom pathlib import Path\nfrom typing import Optional\nfrom pypdf import PdfReader\nPYPDF_IMPORT_ERROR = None']
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in CORE:
            start = min([node.lineno] + [d.lineno for d in node.decorator_list])
            sections.append('\n'.join(source.splitlines()[start - 1:node.end_lineno]))
        elif isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in {'MONTHS', 'MONTH_NUMBERS', 'INVALID_FILENAME_CHARS'} for t in node.targets):
            sections.append(ast.get_source_segment(source, node))
        elif isinstance(node, ast.ClassDef) and node.name == 'App':
            for method in node.body:
                if isinstance(method, ast.FunctionDef) and method.name in {'_next_duplicate_name', '_manual_name_for_type'}:
                    # Sólo sustituye dependencias de widgets por argumentos explícitos.
                    segment = ast.get_source_segment(source, method)
                    lines = segment.splitlines()
                    lines = [lines[0]] + [line[4:] if line.startswith('    ') else line for line in lines[1:]]
                    segment = '\n'.join(lines).replace('self.infos', 'infos').replace('self.company_var.get()', 'company')
                    segment = segment.replace('_next_duplicate_name(self, info: PdfInfo)', 'next_duplicate_name(info: PdfInfo, infos: list[PdfInfo])')
                    segment = segment.replace('_manual_name_for_type(self, info: PdfInfo, choice: str)', 'manual_name_for_type(info: PdfInfo, choice: str, infos: list[PdfInfo], company: str)')
                    sections.append(segment)
    return '\n\n\n'.join(sections) + '\n'


if __name__ == '__main__':
    TARGET.write_text(extract(), encoding='utf-8')
