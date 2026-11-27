"""Reglas nuevas de Declara (rediseño del 26/11/2026, sección 3) que no cambian funciones del motor original.

El motor (`declara_engine`) sigue siendo la fuente de los nombres. Aquí viven el estado de exigibilidad por mes, la fecha
de alta, el nombre manual con su validación y la detección del estándar. Todo es puro: sin disco salvo lo que el motor ya
consulta, sin base de datos.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Optional

from . import declara_engine as motor

# Día límite de los pagos provisionales mensuales. Configurable desde Configuración › Declara.
DUE_DAY = 17

COPIA = 'COPIA IDÉNTICA'
EXCLUIDO = 'EXCLUIDO'
NOT_COUNTED = {'ERROR', 'OMITIDO', 'RFC DIFERENTE', COPIA, EXCLUIDO}

MONTH_BY_NUMBER = {n: m for m, n in motor.MONTH_NUMBERS.items()}
MONTH_LABELS = {
    1: 'Enero', 2: 'Febrero', 3: 'Marzo', 4: 'Abril', 5: 'Mayo', 6: 'Junio',
    7: 'Julio', 8: 'Agosto', 9: 'Septiembre', 10: 'Octubre', 11: 'Noviembre', 12: 'Diciembre',
}  # fmt: skip

COMPLETO, POR_VENCER, VENCIDO, EN_CURSO, FUTURO, NO_APLICA_ALTA = (
    'COMPLETO', 'POR_VENCER', 'VENCIDO', 'EN_CURSO', 'FUTURO', 'NO_APLICA_ALTA',
)  # fmt: skip

CHOICES = {
    'DECLARACION NORMAL': ('DECLARACION', 'Normal', 0),
    'DECLARACION COMPLEMENTARIA': ('DECLARACION', 'Complementaria', 1),
    'ACUSE NORMAL': ('ACUSE', 'Normal', 2),
    'ACUSE COMPLEMENTARIA': ('ACUSE', 'Complementaria', 3),
}
CHOICE_BY_SUFFIX = {suffix: choice for choice, (_k, _t, suffix) in CHOICES.items()}
CHOICE_TEXT = {
    'DECLARACION NORMAL': 'declaración normal',
    'DECLARACION COMPLEMENTARIA': 'declaración complementaria',
    'ACUSE NORMAL': 'acuse normal',
    'ACUSE COMPLEMENTARIA': 'acuse complementaria',
}
FORBIDDEN = re.compile(r'[<>:"/\\|?*]')
RESERVED = re.compile(r'^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\..*)?$', re.IGNORECASE)


# ---------------------------------------------------------------- fecha de alta y exigibilidad


def company_start_date(operations_start: Optional[date], rfc: Optional[str], year: Optional[int] = None):
    """(fecha de alta, origen). La Constancia manda; el RFC de persona moral es sólo el respaldo."""
    if operations_start:
        return operations_start, 'Constancia'
    estimated = motor.rfc_company_start_date(rfc, [year] if year else None)
    return (estimated, 'RFC') if estimated else (None, None)


def due_date(year: int, month: int, due_day: int = DUE_DAY) -> date:
    """El pago del mes vence el día `due_day` del mes siguiente."""
    y, m = (year + 1, 1) if month == 12 else (year, month + 1)
    return date(y, m, due_day)


def counts(info: motor.PdfInfo) -> bool:
    """Si el archivo cuenta en el control mensual."""
    return bool(info.month) and info.status not in NOT_COUNTED and getattr(info, 'count_in_control', True)


def compute_month_status(
    infos: list[motor.PdfInfo],
    year: int,
    start_date: Optional[date] = None,
    today: Optional[date] = None,
    due_day: int = DUE_DAY,
) -> dict[str, dict]:
    """Estado de los 12 meses del ejercicio `year`, aunque no haya PDF de ese año.

    Igual que el original, un mes se completa con declaración normal y acuse normal; las complementarias no lo
    completan. RESICO y SALARIOS normales cuentan como en el original y además se informan aparte.
    """
    today = today or date.today()
    result = {}
    for month, number in motor.MONTH_NUMBERS.items():
        mine = [i for i in infos if i.month == month and str(i.year or '') == str(year) and counts(i)]
        normal = [i for i in mine if motor.norm(i.declaration_type or '') == 'NORMAL']
        declaracion = any(i.document_kind == 'DECLARACION' for i in normal)
        acuse = any(i.document_kind == 'ACUSE' for i in normal)
        due = due_date(year, number, due_day)
        if start_date and (year < start_date.year or (year == start_date.year and number < start_date.month)):
            state = NO_APLICA_ALTA
        elif declaracion and acuse:
            state = COMPLETO
        elif (year, number) == (today.year, today.month):
            state = EN_CURSO
        elif (year, number) > (today.year, today.month):
            state = FUTURO
        elif today <= due:
            state = POR_VENCER
        else:
            state = VENCIDO
        missing = [] if state in {NO_APLICA_ALTA, COMPLETO} else [
            label for ok, label in ((declaracion, 'Declaración normal'), (acuse, 'Acuse normal')) if not ok
        ]  # fmt: skip
        result[month] = {
            'numero': number,
            'estado': state,
            'declaracion': declaracion,
            'acuse': acuse,
            'falta': missing,
            'complementarias': sum(motor.norm(i.declaration_type or '') == 'COMPLEMENTARIA' for i in mine),
            'resico': sum(bool(i.is_resico) for i in mine),
            'salarios': sum(bool(i.is_salarios) for i in mine),
            'vence': due.isoformat(),
            'exigible': state in {POR_VENCER, VENCIDO},
        }
    return result


# ---------------------------------------------------------------- nombres manuales


def manual_name_for_month(
    info: motor.PdfInfo, choice: str, month: str, infos: list[motor.PdfInfo], company: str
) -> Optional[str]:
    """`manual_name_for_type` del original, ampliado para fijar también el mes."""
    canonical = motor.MONTHS.get(motor.norm(month or ''))
    if not canonical:
        return None
    info.month = canonical
    return motor.manual_name_for_type(info, choice, infos, company)


STANDARD = re.compile(
    r'^(?P<major>\d{1,2})(?:\.(?P<minor>\d+))?(?:\.(?P<dup>\d+))?\.-\s+'
    r'(?P<kind>DECLARACION|ACUSE)(?P<comp>\s+COMPLEMENTARIA)?\s+ISR\s+E\s+IVA\s+(?P<month>[A-Z]+)(?:\s+(?P<rest>.*))?$'
)


def detect_standard(name: str) -> Optional[dict]:
    """Lo que significa un nombre que sigue el estándar del despacho, o None.

    `N.-` declaración normal, `N.1.-` complementaria, `N.2.-` acuse normal, `N.3.-` acuse complementaria; un tercer
    número es un sub-consecutivo de copia; RESICO y SALARIOS usan el siguiente decimal libre.
    """
    stem = motor.norm(Path(name).stem if name.lower().endswith('.pdf') else name).strip()
    m = STANDARD.match(stem)
    if not m:
        return None
    month = motor.MONTHS.get(m['month'])
    number = int(m['major'])
    if not month or motor.MONTH_NUMBERS[month] != number:
        return None
    kind = m['kind']
    dtype = 'Complementaria' if m['comp'] else 'Normal'
    choice = f'{kind} {dtype.upper()}'
    minor = int(m['minor']) if m['minor'] is not None else 0
    rest = m['rest'] or ''
    special = [t for t in ('RESICO', 'SALARIOS') if re.search(rf'(?:^|\s){t}(?:\s|$)', rest)]
    if not special and CHOICES[choice][2] != minor:
        return None  # el decimal no corresponde al tipo: no es el estándar
    prefix = (
        f'{m["major"]}'
        + (f'.{m["minor"]}' if m['minor'] is not None else '')
        + (f'.{m["dup"]}' if m['dup'] is not None else '')
    )
    text = f"se detectó '{prefix}.-' = {CHOICE_TEXT[choice]} de {MONTH_LABELS[number].lower()}"
    if special:
        text += ' ' + ' y '.join(special)
    if m['dup'] is not None:
        text += f' (copia {int(m["dup"]) + 1})'
    return {
        'choice': choice,
        'document_kind': kind,
        'declaration_type': dtype,
        'month': month,
        'special': special,
        'duplicate': m['dup'] is not None,
        'texto': text,
    }


def validate_manual_name(
    stem: str, info: motor.PdfInfo, infos: list[motor.PdfInfo], existing: Optional[set[str]] = None
) -> dict:
    """Valida un nombre escrito a mano (sin extensión; `.pdf` se agrega solo).

    Errores: vacío, caracteres prohibidos, nombre reservado de Windows, choque con otro destino del plan o con un
    archivo existente que no forma parte del plan. Aviso si no sigue el estándar.
    """
    clean = (stem or '').strip()
    if clean.lower().endswith('.pdf'):
        clean = clean[:-4].rstrip()
    errors, warnings = [], []
    name = f'{clean}.pdf'
    if not clean:
        errors.append('Escribe un nombre.')
    elif FORBIDDEN.search(clean):
        errors.append('No se permiten los caracteres < > : " / \\ | ? *')
    elif RESERVED.match(clean) or clean.endswith(('.', ' ')):
        errors.append('Windows no admite ese nombre.')
    elif len(name) > 255:
        errors.append('El nombre es demasiado largo.')
    if not errors:
        key = name.casefold()
        planned = {
            j.expected_name.casefold() for j in infos if j is not info and j.expected_name and j.status in {'RENOMBRAR', 'CORRECTO'}
        }  # fmt: skip
        sources = {j.path.name.casefold() for j in infos if j.status == 'RENOMBRAR' and j is not info}
        if key in planned:
            errors.append('Otro archivo del plan ya usa ese nombre.')
        elif key != info.path.name.casefold() and key in {n.casefold() for n in (existing or set())} - sources:
            errors.append('Ya existe un archivo con ese nombre en la carpeta.')
    standard = detect_standard(name) if not errors else None
    if not errors and not standard:
        warnings.append('El nombre no sigue el estándar del despacho.')
    return {'name': name, 'ok': not errors, 'errors': errors, 'warnings': warnings, 'standard': standard}


def apply_manual_name(
    info: motor.PdfInfo,
    name: str,
    count: bool,
    choice: str = '',
    month: str = '',
    year: Optional[str] = None,
) -> None:
    """Deja el archivo en el plan con el nombre dado. Si cuenta, fija documento, tipo, mes y ejercicio."""
    info.expected_name = name
    info.status = 'RENOMBRAR' if info.path.name.casefold() != name.casefold() else 'CORRECTO'
    info.manual_override = True
    info.origin = 'manual'
    info.count_in_control = bool(count)
    if count:
        kind, dtype, _suffix = CHOICES[choice]
        info.document_kind, info.declaration_type = kind, dtype
        info.month = motor.MONTHS.get(motor.norm(month))
        if year and not info.year:
            info.year = str(year)
    info.detail = 'Renombrado manualmente' + ('.' if count else '; no cuenta en el control mensual.')
