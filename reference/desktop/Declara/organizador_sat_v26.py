from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import queue
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from wheel_support import WheelSupport

try:
    from pypdf import PdfReader
except Exception as exc:
    PdfReader = None
    PYPDF_IMPORT_ERROR = exc
else:
    PYPDF_IMPORT_ERROR = None

APP_TITLE = "Declara · ContaSuite"
APP_VERSION = "v0.2.6 beta"
MONTHS = {
    "ENERO": "ENERO", "FEBRERO": "FEBRERO", "MARZO": "MARZO", "ABRIL": "ABRIL",
    "MAYO": "MAYO", "JUNIO": "JUNIO", "JULIO": "JULIO", "AGOSTO": "AGOSTO",
    "SEPTIEMBRE": "SEPTIEMBRE", "SETIEMBRE": "SEPTIEMBRE", "OCTUBRE": "OCTUBRE",
    "NOVIEMBRE": "NOVIEMBRE", "DICIEMBRE": "DICIEMBRE",
}
MONTH_NUMBERS = {
    "ENERO": 1, "FEBRERO": 2, "MARZO": 3, "ABRIL": 4,
    "MAYO": 5, "JUNIO": 6, "JULIO": 7, "AGOSTO": 8,
    "SEPTIEMBRE": 9, "OCTUBRE": 10, "NOVIEMBRE": 11, "DICIEMBRE": 12,
}
INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*]+')

SAT_PORTAL_URL = "https://www.sat.gob.mx/portal/public/home"
SAT_DECLARACIONES_URL = "https://www.sat.gob.mx/portal/public/personas-morales/general-de-ley-personas-morales"


def get_playwright_browser_dir() -> Path:
    """Ruta persistente compartida entre el instalador y el EXE.

    Evita que PyInstaller/Playwright busque Firefox dentro de la carpeta
    temporal _MEI... usada por ejecutables --onefile.
    """
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "OrganizadorSAT" / "playwright-browsers"
    return Path.home() / ".organizador_sat" / "playwright-browsers"


PLAYWRIGHT_BROWSER_DIR = get_playwright_browser_dir()
# Debe definirse ANTES de importar/iniciar Playwright. El BAT de instalación
# usa exactamente la misma ruta.
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(PLAYWRIGHT_BROWSER_DIR)

def playwright_firefox_present() -> bool:
    try:
        return any(p.is_dir() for p in PLAYWRIGHT_BROWSER_DIR.glob("firefox-*"))
    except Exception:
        return False

def unique_download_path(folder: Path, filename: str) -> Path:
    """Devuelve una ruta libre sin sobrescribir descargas existentes."""
    safe_name = Path(filename).name or "descarga.pdf"
    candidate = folder / safe_name
    if not candidate.exists():
        return candidate
    stem, suffix = candidate.stem, candidate.suffix
    n = 1
    while True:
        alt = folder / f"{stem} ({n}){suffix}"
        if not alt.exists():
            return alt
        n += 1



@dataclass
class PdfInfo:
    path: Path
    rfc: Optional[str] = None
    razon_social: Optional[str] = None
    declaration_type: Optional[str] = None
    complement_type: Optional[str] = None
    month: Optional[str] = None
    year: Optional[str] = None
    operation: Optional[str] = None
    document_kind: Optional[str] = None
    expected_name: Optional[str] = None
    status: str = ""
    detail: str = ""
    sha256: Optional[str] = None
    is_resico: bool = False
    is_salarios: bool = False
    preserve_special_name: bool = False
    complement_sequence: Optional[str] = None
    manual_override: bool = False

    @property
    def expected_path(self) -> Optional[Path]:
        return self.path.with_name(self.expected_name) if self.expected_name else None


def strip_accents(text: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch))


def norm(text: str) -> str:
    return strip_accents(text).upper().replace("\u00A0", " ")


def sanitize_company_name(name: str) -> str:
    name = INVALID_FILENAME_CHARS.sub(" ", name.strip())
    return re.sub(r"\s+", " ", name).upper().strip(" .")


def add_duplicate_suffix(filename: str, number: int) -> str:
    """Agrega un sub-consecutivo ordenado a un nombre estándar.

    Ejemplos:
    - "1.- DECLARACION ...pdf" -> "1.0.1.- DECLARACION ...pdf"
    - "1.2.- ACUSE ...pdf" -> "1.2.1.- ACUSE ...pdf"

    Si ``number`` es 2, genera el primer duplicado; si es 3, el segundo, etc.
    """
    path = Path(filename)
    m = re.match(r"^(\d+)(?:\.(\d+))?\.\-\s*(.+)$", path.stem, flags=re.IGNORECASE)
    if not m:
        # Respaldo por si el nombre no sigue el patrón esperado.
        return f"{path.stem} {number}{path.suffix or '.pdf'}"
    major = m.group(1)
    minor = m.group(2)
    rest = m.group(3)
    dup = max(1, int(number) - 1)
    if minor is None:
        new_prefix = f"{major}.0.{dup}"
    else:
        new_prefix = f"{major}.{minor}.{dup}"
    return f"{new_prefix}.- {rest}{path.suffix or '.pdf'}"


def _existing_copy_index(current_name: str, base_name: str) -> int:
    """Devuelve 1 para el nombre base y 2/3/... para sub-consecutivos válidos.

    Se usa para conservar, cuando sea posible, nombres que ya estén correctamente
    ordenados como "1.2.1.- ...", "1.2.2.- ...", etc.
    """
    if current_name.casefold() == base_name.casefold():
        return 1

    base = Path(base_name)
    cur = Path(current_name)

    base_m = re.match(r"^(\d+)(?:\.(\d+))?\.\-\s*(.+)$", base.stem, flags=re.IGNORECASE)
    cur_m = re.match(r"^(\d+)(?:\.(\d+))(?:\.(\d+))?\.\-\s*(.+)$", cur.stem, flags=re.IGNORECASE)
    if base_m and cur_m:
        b_major, b_minor, b_rest = base_m.group(1), base_m.group(2), base_m.group(3)
        c_major, c_minor, c_dup, c_rest = cur_m.group(1), cur_m.group(2), cur_m.group(3), cur_m.group(4)
        expected_minor = b_minor if b_minor is not None else '0'
        if (
            c_major == b_major
            and c_minor == expected_minor
            and c_dup is not None
            and c_rest.casefold() == b_rest.casefold()
        ):
            try:
                return int(c_dup) + 1
            except ValueError:
                pass

    # Respaldo legado para nombres tipo "... 2.pdf"
    m = re.fullmatch(re.escape(base.stem) + r"\s+(\d+)", cur.stem, flags=re.IGNORECASE)
    if m:
        try:
            n = int(m.group(1))
            return n if n >= 2 else 999999
        except ValueError:
            pass
    return 999999


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def first_page_text(path: Path) -> str:
    if PdfReader is None:
        raise RuntimeError(f"No se pudo cargar pypdf: {PYPDF_IMPORT_ERROR}")
    reader = PdfReader(str(path))
    if not reader.pages:
        return ""
    return reader.pages[0].extract_text() or ""


def all_pages_text(path: Path, max_pages: int = 8) -> str:
    """Extrae texto de varias páginas como respaldo para formatos especiales.

    Se limita a unas cuantas páginas para mantener el análisis ágil.
    """
    if PdfReader is None:
        raise RuntimeError(f"No se pudo cargar pypdf: {PYPDF_IMPORT_ERROR}")
    reader = PdfReader(str(path))
    chunks = []
    for page in reader.pages[:max_pages]:
        try:
            chunks.append(page.extract_text() or "")
        except Exception:
            continue
    return "\n".join(chunks)


def _find(pattern: str, text: str, flags=re.IGNORECASE) -> Optional[str]:
    m = re.search(pattern, text, flags)
    return m.group(1).strip() if m else None


def parse_pdf(path: Path, company: str) -> PdfInfo:
    info = PdfInfo(path=path)
    name_text = norm(path.stem)
    # RESICO/SALARIOS pueden venir con una plantilla cuyo texto interno no
    # permite recuperar RFC/ejercicio. Para esos archivos el nombre visible
    # es una fuente válida SOLO para clasificar y numerar; no se aplica este
    # fallback a los demás PDFs.
    name_is_resico = "RESICO" in name_text or "REGIMEN SIMPLIFICADO DE CONFIANZA" in name_text
    name_is_salarios = "SALARIOS" in name_text
    name_is_special = name_is_resico or name_is_salarios

    try:
        text = first_page_text(path)
    except Exception as exc:
        if name_is_special:
            text = ""
        else:
            info.status = "ERROR"
            info.detail = f"No se pudo leer el PDF: {exc}"
            return info

    ntext = norm(text) if text else ""
    info.is_resico = (
        "RESICO" in ntext
        or "REGIMEN SIMPLIFICADO DE CONFIANZA" in ntext
        or name_is_resico
    )
    info.is_salarios = name_is_salarios
    is_special_name = info.is_resico or info.is_salarios

    if not text.strip() and not is_special_name:
        info.status = "OMITIDO"
        info.detail = "La primera página no contiene texto extraíble."
        return info

    if "ACUSE DE RECIBO" in ntext and "DECLARACION PROVISIONAL O DEFINITIVA DE IMPUESTOS FEDERALES" in ntext:
        info.document_kind = "ACUSE"
    elif "DECLARACION PROVISIONAL O DEFINITIVA DE IMPUESTOS FEDERALES" in ntext:
        info.document_kind = "DECLARACION"
    elif is_special_name:
        # Excepción solicitada: los archivos RESICO o SALARIOS pueden usar una
        # plantilla SAT distinta. Solo en esos casos se permite inferir el tipo
        # desde el nombre del archivo; el resto mantiene la detección estricta.
        if "ACUSE" in name_text:
            info.document_kind = "ACUSE"
        elif "DECLARACION" in name_text:
            info.document_kind = "DECLARACION"
        else:
            info.status = "OMITIDO"
            info.detail = "Archivo RESICO/SALARIOS: no se pudo inferir si es declaración o acuse desde el nombre."
            return info
    else:
        info.status = "OMITIDO"
        info.detail = "No se identificó como declaración o acuse SAT."
        return info

    info.rfc = _find(r"RFC\s*:\s*([A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3})", text)
    info.razon_social = _find(r"Denominaci[oó]n\s+o\s+raz[oó]n\s+social\s*:\s*([^\r\n]+)", text)
    info.declaration_type = _find(r"Tipo\s+de\s+declaraci[oó]n\s*:\s*([A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+)", text)
    info.complement_type = _find(r"Tipo\s+de\s+complementaria\s*:\s*([^\r\n]+)", text)

    # Algunos archivos ya vienen renombrados desde origen y el texto interno
    # puede indicar "Normal" aunque el nombre identifique claramente que es
    # una complementaria. En ese caso el nombre del archivo tiene prioridad
    # para evitar que choque con la declaración/acuse normal del mismo mes.
    # Para archivos especiales RESICO/SALARIOS el nombre puede contener la
    # clasificación más útil que el texto interno. COMP también se interpreta
    # como complementaria, pero SOLO para estos casos especiales.
    name_marks_complement = (
        "COMPLEMENTARIA" in name_text
        or re.search(r"(?:^|[ _.-])COMPL(?:$|[ _.-])", name_text)
        or (is_special_name and re.search(r"(?:^|[ _.-])COMP(?:$|[ _.-])", name_text))
    )
    if name_marks_complement:
        info.declaration_type = "Complementaria"
        # Puede haber más de una complementaria del mismo mes. Cuando el nombre
        # ya trae un consecutivo (por ejemplo, "COMPL 2" o
        # "COMPLEMENTARIA (3)"), se conserva para evitar conflictos sin
        # alterar la posición base de la complementaria (N.1 o N.3).
        seq = re.search(r"(?:COMPLEMENTARIA|COMPL|COMP)[ _.-]*(?:\(|\[)?(\d+)(?:\)|\])?\s*$", name_text)
        if not seq:
            seq = re.search(r"(?:\(|\[)?(\d+)(?:\)|\])?\s*$", name_text)
        if seq:
            info.complement_sequence = seq.group(1)
    elif is_special_name and not info.declaration_type:
        info.declaration_type = "Normal"

    raw_month = _find(r"Per[ií]odo\s+de\s+la\s+declaraci[oó]n\s*:\s*([A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+)", text)
    info.year = _find(r"Ejercicio\s*:\s*(\d{4})", text)
    info.operation = _find(r"N[uú]mero\s+de\s+operaci[oó]n\s*:\s*(\d+)", text)
    if raw_month:
        info.month = MONTHS.get(norm(raw_month))
    if not info.month and is_special_name:
        # Fallback exclusivo para RESICO/SALARIOS: toma el mes del nombre.
        for alias, canonical in MONTHS.items():
            if re.search(rf"(?:^|[ _.-]){re.escape(alias)}(?:$|[ _.-])", name_text):
                info.month = canonical
                break

    # Algunos formatos RESICO/SALARIOS no exponen RFC, periodo o ejercicio
    # en la primera página. Antes de omitirlos, revisamos varias páginas del
    # mismo PDF. Esto solo se usa como respaldo para archivos especiales.
    if is_special_name and (not info.rfc or not info.month or not info.year):
        try:
            full_text = all_pages_text(path)
        except Exception:
            full_text = ""
        if full_text:
            if not info.rfc:
                info.rfc = _find(r"RFC\s*:\s*([A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3})", full_text)
            if not info.razon_social:
                info.razon_social = _find(r"Denominaci[oó]n\s+o\s+raz[oó]n\s+social\s*:\s*([^\r\n]+)", full_text)
            if not info.month:
                raw_month_full = _find(r"Per[ií]odo\s+de\s+la\s+declaraci[oó]n\s*:\s*([A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+)", full_text)
                if raw_month_full:
                    info.month = MONTHS.get(norm(raw_month_full))
            if not info.year:
                info.year = _find(r"Ejercicio\s*:\s*(\d{4})", full_text)
            if not info.operation:
                info.operation = _find(r"N[uú]mero\s+de\s+operaci[oó]n\s*:\s*(\d+)", full_text)

    missing = []
    if not info.rfc: missing.append("RFC")
    if not info.month: missing.append("periodo")
    if not info.year: missing.append("ejercicio")
    if not info.declaration_type: missing.append("tipo de declaración")
    if missing:
        # Excepción MUY acotada para RESICO/SALARIOS: si el nombre ya dice
        # claramente qué documento es y de qué mes, no se omite por faltar
        # RFC/ejercicio dentro del PDF. En ese caso se conserva literalmente
        # el nombre actual y después solo se antepone la numeración dinámica.
        allowed_missing = set(missing).issubset({"RFC", "ejercicio"})
        if is_special_name and info.month and info.document_kind and info.declaration_type and allowed_missing:
            info.preserve_special_name = True
        else:
            info.status = "OMITIDO"
            info.detail = "No se pudo identificar: " + ", ".join(missing)
            return info

    dtype = norm(info.declaration_type)
    month_number = MONTH_NUMBERS.get(info.month)
    if not month_number:
        info.status = "OMITIDO"
        info.detail = f"No se pudo asignar numeración al periodo: {info.month}"
        return info

    # Numeración normal fija por mes y tipo de documento:
    # N.-   Declaración normal
    # N.1.- Declaración complementaria
    # N.2.- Acuse normal
    # N.3.- Acuse complementaria
    #
    # Los RESICO NO usan una posición fija. Su número se asigna después, al
    # analizar toda la carpeta, tomando el siguiente decimal disponible tras
    # el documento normal con numeración más alta que realmente exista.
    # Ejemplo: si mayo tiene 5.- y 5.2.-, el primer RESICO será 5.3.-.
    if info.is_resico or info.is_salarios:
        special = "RESICO" if info.is_resico else "SALARIOS"
        if (info.document_kind, dtype) not in {
            ("DECLARACION", "NORMAL"), ("DECLARACION", "COMPLEMENTARIA"),
            ("ACUSE", "NORMAL"), ("ACUSE", "COMPLEMENTARIA")
        }:
            info.status = "OMITIDO"
            info.detail = f"Tipo de declaración {special} no contemplado: {info.declaration_type}"
            return info
        info.status = "PENDIENTE ESPECIAL"
        info.detail = f"{special} pendiente de numeración dinámica."
        return info

    if info.document_kind == "DECLARACION" and dtype == "NORMAL":
        final = f"{month_number}.- DECLARACION ISR E IVA {info.month} {company}.pdf"
    elif info.document_kind == "DECLARACION" and dtype == "COMPLEMENTARIA":
        extra = f" {info.complement_sequence}" if info.complement_sequence else ""
        final = f"{month_number}.1.- DECLARACION COMPLEMENTARIA ISR E IVA {info.month} {company}{extra}.pdf"
    elif info.document_kind == "ACUSE" and dtype == "NORMAL":
        final = f"{month_number}.2.- ACUSE ISR E IVA {info.month} {company}.pdf"
    elif info.document_kind == "ACUSE" and dtype == "COMPLEMENTARIA":
        extra = f" {info.complement_sequence}" if info.complement_sequence else ""
        final = f"{month_number}.3.- ACUSE COMPLEMENTARIA ISR E IVA {info.month} {company}{extra}.pdf"
    else:
        info.status = "OMITIDO"
        info.detail = f"Tipo de declaración no contemplado: {info.declaration_type}"
        return info

    info.expected_name = final
    if path.name.casefold() == final.casefold():
        info.status = "CORRECTO"
        info.detail = "Ya tiene el nombre estándar."
    else:
        info.status = "RENOMBRAR"
        info.detail = "Listo para renombrar."
    return info


def analyze_folder(folder: Path, company: str) -> list[PdfInfo]:
    pdfs = sorted((p for p in folder.iterdir() if p.is_file() and p.suffix.lower() == ".pdf"), key=lambda p: p.name.casefold())
    infos = [parse_pdf(p, company) for p in pdfs]

    # Rescate especial para RESICO/SALARIOS sin periodo legible.
    # Si el nombre identifica claramente documento + complementaria/normal pero
    # no trae mes y el PDF tampoco lo expone, intentamos emparejarlo con su
    # contraparte (declaración <-> acuse) del mismo tipo especial. Solo se usa
    # cuando existe UN ÚNICO mes candidato; nunca se adivina entre varios.
    for i in infos:
        if i.status != "OMITIDO" or not (i.is_resico or i.is_salarios) or i.month:
            continue
        if not i.document_kind or not i.declaration_type:
            continue
        dtype = norm(i.declaration_type or "")
        if dtype not in {"NORMAL", "COMPLEMENTARIA"}:
            continue
        candidate_months = set()
        for j in infos:
            if j is i or not j.month:
                continue
            if bool(j.is_resico) != bool(i.is_resico) or bool(j.is_salarios) != bool(i.is_salarios):
                continue
            if norm(j.declaration_type or "") != dtype:
                continue
            if j.document_kind == i.document_kind:
                continue
            candidate_months.add(j.month)
        if len(candidate_months) == 1:
            i.month = next(iter(candidate_months))
            i.status = "PENDIENTE ESPECIAL"
            i.preserve_special_name = False
            i.detail = f"Periodo inferido por contraparte especial del mismo tipo: {i.month}."

    # Asigna numeración dinámica a archivos especiales RESICO y SALARIOS.
    # Los documentos normales conservan sus posiciones fijas N, N.1, N.2 y N.3.
    # Los especiales toman el siguiente decimal disponible real del mes para no
    # competir con los documentos ordinarios.
    regular_suffix = {
        ("DECLARACION", "NORMAL"): 0,
        ("DECLARACION", "COMPLEMENTARIA"): 1,
        ("ACUSE", "NORMAL"): 2,
        ("ACUSE", "COMPLEMENTARIA"): 3,
    }
    special_order = {
        ("DECLARACION", "NORMAL"): 0,
        ("DECLARACION", "COMPLEMENTARIA"): 1,
        ("ACUSE", "NORMAL"): 2,
        ("ACUSE", "COMPLEMENTARIA"): 3,
    }

    months = sorted({i.month for i in infos if i.month}, key=lambda m: MONTH_NUMBERS.get(m, 99))
    for month in months:
        month_number = MONTH_NUMBERS.get(month)
        if not month_number:
            continue

        occupied = []
        for i in infos:
            if i.month != month or i.is_resico or i.is_salarios or i.status in {"ERROR", "OMITIDO"}:
                continue
            dtype = norm(i.declaration_type or "")
            suffix = regular_suffix.get((i.document_kind or "", dtype))
            if suffix is not None:
                occupied.append(suffix)

        next_suffix = (max(occupied) + 1) if occupied else 1
        specials = [
            i for i in infos
            if i.month == month and (i.is_resico or i.is_salarios) and i.status == "PENDIENTE ESPECIAL"
        ]
        specials.sort(key=lambda i: (
            0 if i.is_resico else 1,
            special_order.get((i.document_kind or "", norm(i.declaration_type or "")), 99),
            i.operation or "",
            i.path.name.casefold(),
        ))

        for offset, i in enumerate(specials):
            suffix = next_suffix + offset
            dtype = norm(i.declaration_type or "")
            if i.document_kind == "DECLARACION" and dtype == "NORMAL":
                label = "DECLARACION ISR E IVA"
            elif i.document_kind == "DECLARACION" and dtype == "COMPLEMENTARIA":
                label = "DECLARACION COMPLEMENTARIA ISR E IVA"
            elif i.document_kind == "ACUSE" and dtype == "NORMAL":
                label = "ACUSE ISR E IVA"
            elif i.document_kind == "ACUSE" and dtype == "COMPLEMENTARIA":
                label = "ACUSE COMPLEMENTARIA ISR E IVA"
            else:
                i.status = "OMITIDO"
                i.detail = f"Tipo especial no contemplado: {i.declaration_type}"
                continue

            tags = []
            if i.is_resico:
                tags.append("RESICO")
            if i.is_salarios:
                tags.append("SALARIOS")
            special_desc = "/".join(tags) if tags else "ESPECIAL"

            if i.preserve_special_name:
                # Caso especial: no inventar ni normalizar texto que el PDF no
                # permite validar. Se conserva el nombre tal como está y solo
                # se agrega el prefijo numérico correspondiente al mes.
                base = re.sub(r"^\d+(?:\.\d+)?\.-\s*", "", i.path.stem, flags=re.IGNORECASE).strip()
                final = f"{month_number}.{suffix}.- {base}.pdf"
            else:
                tag_text = " " + " ".join(tags) if tags else ""
                seq_text = f" {i.complement_sequence}" if (dtype == "COMPLEMENTARIA" and i.complement_sequence) else ""
                final = f"{month_number}.{suffix}.- {label} {month} {company}{tag_text}{seq_text}.pdf"

            i.expected_name = final
            if i.path.name.casefold() == final.casefold():
                i.status = "CORRECTO"
                i.detail = f"{special_desc} ya tiene la numeración dinámica correcta ({month_number}.{suffix})."
            else:
                i.status = "RENOMBRAR"
                if i.preserve_special_name:
                    i.detail = f"{special_desc}: metadatos internos incompletos; se conserva el nombre y solo se antepone {month_number}.{suffix}.-"
                else:
                    i.detail = f"{special_desc}: siguiente número disponible del mes = {month_number}.{suffix}."

    rfcs = [i.rfc for i in infos if i.rfc and i.status not in {"ERROR", "OMITIDO"}]
    primary_rfc = Counter(rfcs).most_common(1)[0][0] if rfcs else None
    if primary_rfc:
        for i in infos:
            if i.rfc and i.rfc != primary_rfc and i.status in {"RENOMBRAR", "CORRECTO"}:
                i.status = "RFC DIFERENTE"
                i.detail = f"RFC {i.rfc}; el RFC principal detectado es {primary_rfc}."

    # Resolver colisiones de nombre automáticamente.
    # Si dos o más PDFs requieren exactamente el mismo nombre final, el
    # primero conserva el nombre estándar y los siguientes reciben " 2",
    # " 3", etc. antes de .pdf. Así ya no quedan como CONFLICTO/DUPLICADO.
    by_target: dict[str, list[PdfInfo]] = defaultdict(list)
    for i in infos:
        if i.expected_name and i.status in {"RENOMBRAR", "CORRECTO"}:
            by_target[i.expected_name.casefold()].append(i)

    for group in by_target.values():
        if len(group) <= 1:
            continue
        base_name = group[0].expected_name
        # Conserva primero el nombre base si ya existe; después, nombres que
        # ya tengan un consecutivo válido; finalmente los crudos/nuevos.
        group.sort(key=lambda i: (
            _existing_copy_index(i.path.name, base_name),
            0 if i.status == "CORRECTO" else 1,
            i.operation or "",
            i.path.name.casefold(),
        ))
        for idx, i in enumerate(group, start=1):
            assigned = base_name if idx == 1 else add_duplicate_suffix(base_name, idx)
            i.expected_name = assigned
            if i.path.name.casefold() == assigned.casefold():
                i.status = "CORRECTO"
                i.detail = "Ya tiene el nombre estándar/consecutivo correcto."
            else:
                i.status = "RENOMBRAR"
                if idx == 1:
                    i.detail = "Listo para renombrar."
                else:
                    i.detail = f"Nombre repetido resuelto automáticamente con consecutivo {idx}."

    # Segunda protección: si el nombre calculado ya existe en la carpeta y no
    # forma parte del mismo plan de renombrado, buscar el siguiente consecutivo
    # libre en lugar de marcar CONFLICTO o DUPLICADO.
    planned_sources = {i.path.resolve() for i in infos if i.status in {"RENOMBRAR", "CORRECTO"}}
    reserved_targets = {
        str(i.expected_path.resolve()).casefold()
        for i in infos if i.expected_path and i.status in {"RENOMBRAR", "CORRECTO"}
    }
    for i in infos:
        if i.status != "RENOMBRAR" or not i.expected_path:
            continue
        target = i.expected_path
        if target.resolve() == i.path.resolve():
            continue
        if target.exists() and target.resolve() not in planned_sources:
            base_name = i.expected_name
            n = 2
            while True:
                candidate_name = add_duplicate_suffix(base_name, n)
                candidate = i.path.with_name(candidate_name)
                key = str(candidate.resolve()).casefold()
                if (not candidate.exists() or candidate.resolve() == i.path.resolve()) and key not in reserved_targets:
                    reserved_targets.discard(str(target.resolve()).casefold())
                    i.expected_name = candidate_name
                    reserved_targets.add(key)
                    i.detail = f"El nombre estándar ya existía; se usará el consecutivo {n}."
                    break
                n += 1

    return infos



def rfc_company_start_date(rfc: Optional[str], reference_years: list[int] | None = None) -> Optional[date]:
    """Obtiene la fecha de constitución codificada en un RFC de persona moral.

    Solo aplica a RFC de 12 caracteres: AAA + AAMMDD + homoclave. En RFC de
    persona física (13 caracteres) esos dígitos representan fecha de nacimiento,
    por lo que deliberadamente NO se usan para omitir meses.
    """
    if not rfc:
        return None
    value = norm(rfc).replace(" ", "").replace("-", "")
    m = re.fullmatch(r"[A-ZÑ&]{3}(\d{2})(\d{2})(\d{2})[A-Z0-9]{3}", value)
    if not m:
        return None
    yy, mm, dd = map(int, m.groups())
    refs = sorted(set(reference_years or []), reverse=True)
    ref_year = refs[0] if refs else date.today().year
    candidates = [1900 + yy, 2000 + yy]
    plausible = [y for y in candidates if y <= ref_year]
    year = max(plausible) if plausible else min(candidates)
    try:
        return date(year, mm, dd)
    except ValueError:
        return None


def compute_month_completeness(
    infos: list[PdfInfo],
    primary_rfc: Optional[str] = None,
    today: Optional[date] = None,
) -> dict[str, dict[str, dict[str, object]]]:
    """Resume por ejercicio si cada mes tiene al menos una declaración y un acuse.

    Reglas:
    - Las complementarias NO cuentan para completar el mes.
    - Para RFC de persona moral, los meses anteriores al mes de alta codificado
      en el RFC se marcan como no aplicables en el ejercicio de alta.
    - Un periodo mensual se vuelve exigible hasta el mes siguiente. Por ejemplo,
      OCTUBRE no se marca como faltante durante octubre; comienza a evaluarse en
      noviembre. Los meses futuros tampoco se consideran pendientes.
    """
    current = today or date.today()
    years = sorted({i.year for i in infos if i.year and i.month}, reverse=True)
    numeric_years = [int(y) for y in years if str(y).isdigit()]
    start_date = rfc_company_start_date(primary_rfc, numeric_years)
    result: dict[str, dict[str, dict[str, object]]] = {}

    for year in years:
        year_data: dict[str, dict[str, object]] = {}
        ynum = int(year) if str(year).isdigit() else None

        for month in MONTH_NUMBERS:
            month_num = MONTH_NUMBERS[month]
            applicable = True
            reason = None

            # Regla por fecha de alta de la persona moral.
            if start_date and ynum is not None:
                if ynum < start_date.year:
                    applicable = False
                    reason = "ALTA"
                elif ynum == start_date.year and month_num < start_date.month:
                    applicable = False
                    reason = "ALTA"

            # Regla de exigibilidad mensual: el mes se presenta/evalúa hasta el
            # mes siguiente. El mes actual y los futuros aún no son faltantes.
            if applicable and ynum is not None:
                if ynum > current.year:
                    applicable = False
                    reason = "NO_EXIGIBLE"
                elif ynum == current.year and month_num >= current.month:
                    applicable = False
                    reason = "NO_EXIGIBLE"

            year_data[month] = {
                "declaracion": False,
                "acuse": False,
                "aplicable": applicable,
                "razon_no_aplica": reason,
            }

        for i in infos:
            if i.year != year or not i.month:
                continue
            if i.status in {"ERROR", "OMITIDO", "RFC DIFERENTE"}:
                continue
            dtype = norm(i.declaration_type or "")
            if dtype == "COMPLEMENTARIA":
                continue
            if dtype != "NORMAL":
                continue
            if i.document_kind == "DECLARACION":
                year_data[i.month]["declaracion"] = True
            elif i.document_kind == "ACUSE":
                year_data[i.month]["acuse"] = True

        result[year] = year_data
    return result

def execute_renames(infos: list[PdfInfo]) -> tuple[int, list[str]]:
    plan = [i for i in infos if i.status == "RENOMBRAR" and i.expected_path]
    if not plan:
        return 0, []
    source_paths = {i.path.resolve() for i in plan}
    target_keys = [str(i.expected_path.resolve()).casefold() for i in plan]
    if len(target_keys) != len(set(target_keys)):
        return 0, ["Hay destinos duplicados en el plan. Vuelve a analizar antes de procesar."]
    errors = []
    for i in plan:
        t = i.expected_path
        if t and t.exists() and t.resolve() not in source_paths and t.resolve() != i.path.resolve():
            errors.append(f"Ya existe: {t.name}")
    if errors:
        return 0, errors

    temp_moves: list[tuple[Path, Path, Path]] = []
    try:
        for index, i in enumerate(plan, start=1):
            src, target = i.path, i.expected_path
            fd, temp_name = tempfile.mkstemp(prefix=f".__SAT_RENAME_{index}_", suffix=".pdf", dir=str(src.parent))
            os.close(fd)
            temp_path = Path(temp_name)
            temp_path.unlink(missing_ok=True)
            src.rename(temp_path)
            temp_moves.append((temp_path, src, target))
        completed = []
        for temp_path, original, target in temp_moves:
            temp_path.rename(target)
            completed.append((target, original))
        return len(completed), []
    except Exception as exc:
        for temp_path, original, target in reversed(temp_moves):
            try:
                if temp_path.exists() and not original.exists(): temp_path.rename(original)
                elif target.exists() and not original.exists(): target.rename(original)
            except Exception:
                pass
        return 0, [f"Error durante el renombrado: {exc}"]


# ══════════════════════════════════════════════════════════════════════════════
# INTERFAZ · Todo lo anterior es el motor (análisis, nombres, meses) y no cambia.
# La interfaz usa el kit visual compartido de ContaSuite (suite_ui.py).
# ══════════════════════════════════════════════════════════════════════════════
import json
from suite_ui import (COMMON_SHORTCUTS, Card, Dialog, Look, MetricCard, ScrollArea, Shell, autowrap, enable_high_dpi,
                      env_size, env_theme, install_shortcuts, normalize_size, normalize_theme)
from suite_ui import show_help as show_help_dialog

CONFIG_PATH = Path(os.getenv("APPDATA") or Path.home()) / "ContaSuite" / "Declara" / "config.json"
FILTERS = ["TODOS", "RENOMBRAR", "CORRECTO", "RESICO", "SALARIOS", "CONFLICTO", "DUPLICADO", "OMITIDO/ERROR"]
STEPS = [("Empresa", "Carpeta y nombre corto"), ("Análisis", "Revisa los PDF"), ("Renombrado", "Aplica los nombres")]
TREE_TAGS = {"CORRECTO": ("success_bg", "text"), "RENOMBRAR": ("warn_bg", "text"), "RESICO": ("info_bg", "text"),
             "CONFLICTO": ("error_bg", "text"), "DUPLICADO": ("neutral_bg", "text"), "OMITIDO": ("neutral_bg", "muted"),
             "ERROR": ("error_bg", "text"), "RFC DIFERENTE": ("error_bg", "text")}


class App(tk.Tk):
    def __init__(self):
        enable_high_dpi()
        super().__init__()
        self.title(f"{APP_TITLE} {APP_VERSION}")
        saved = self._read_config()
        self.look = Look(self, "declara", APP_VERSION.lstrip("v"), env_theme() or normalize_theme(saved.get("theme")),
                         normalize_size(saved.get("font") or env_size() or "Normal"))
        self.look.apply()
        px = self.look.px
        w = min(px(1240), self.winfo_screenwidth() - 60); h = min(px(820), self.winfo_screenheight() - 90)
        self.geometry(f"{w}x{h}")
        self.minsize(min(px(940), w), min(px(620), h))
        self.infos: list[PdfInfo] = []
        self.filter_var = tk.StringVar(value="TODOS")
        self.folder_var = tk.StringVar()
        self.company_var = tk.StringVar()
        self.summary_var = tk.StringVar(value="Selecciona una carpeta y escribe el nombre corto de la empresa.")
        self.rfc_var = tk.StringVar(value="RFC detectado: -")
        self.detail_var = tk.StringVar(value="Selecciona un PDF para ver sus detalles.")
        self.months_var = tk.StringVar(value="Analiza la carpeta para revisar qué meses están completos o pendientes.")
        self.months_data = {}
        self.company_start_date = None
        self.analyzed_folder: Optional[Path] = None
        self.browser_running = False
        self.browser_declarations_mode = False
        self.bulk_download_running = False
        self.browser_result_queue = queue.Queue()
        self.browser_command_queue = queue.Queue()
        self.browser_event_queue = queue.Queue()
        self.browser_status_var = tk.StringVar(value="SAT: analiza una carpeta para habilitar accesos y fijar la ruta de descarga.")
        self.metric_vars: dict[str, tk.StringVar] = {}
        self._build_ui()
        from company_context import apply_company
        apply_company(self, 'declara')
        from print_bridge import attach_print_button
        attach_print_button(self,lambda:[self.infos[int(i)].path for i in self.tree.selection()],lambda:self.folder_var.get())
        self.wheel = WheelSupport(self)
        self.folder_var.trace_add("write", self._on_folder_changed)
        self.folder_var.trace_add("write", lambda *_: self._update_steps())
        self.company_var.trace_add("write", lambda *_: self._update_steps())
        self.look.on_change(self._save_config)
        install_shortcuts(self, self.look, self.show_help)
        self.after(300, self._poll_browser_results)
        self.after(150, self._place_sash)
        self._update_steps()

    # ------------------------------------------------------------------ preferencias
    def _read_config(self) -> dict:
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save_config(self):
        try:
            CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            CONFIG_PATH.write_text(json.dumps({"theme": self.look.theme, "font": self.look.size}, indent=2), encoding="utf-8")
        except OSError:
            pass

    # ------------------------------------------------------------------ construcción de la interfaz
    def _build_ui(self):
        L = self.look; px = L.px
        self.shell = Shell(self, L, self.summary_var, steps=STEPS, section="Flujo de trabajo",
                           note="No se sobrescribe ningún archivo. Los PDF descargados del SAT se guardan en la carpeta de la empresa.",
                           title="Declaraciones SAT",
                           subtitle="Analiza, renombra y clasifica declaraciones y acuses; controla los meses y descarga desde el portal.",
                           on_help=self.show_help)
        ttk.Label(self.shell.actions, textvariable=self.rfc_var, style="BadgeInfo.TLabel").pack(side="left")
        content = self.shell.content
        content.columnconfigure(0, weight=1); content.rowconfigure(0, weight=1)
        self.panes = L.paned(content, "vertical")
        self.panes.grid(row=0, column=0, sticky="nsew")
        self.scroller = ScrollArea(self.panes, L, bg="bg", style="Bg.TFrame")
        top = self.scroller.inner
        top.columnconfigure(0, weight=1)

        # ---- empresa
        company = Card(top, L, "Empresa")
        company.grid(row=0, column=0, sticky="ew", pady=(0, px(10)))
        form = ttk.Frame(company.body, style="Card.TFrame"); form.pack(fill="x"); form.columnconfigure(1, weight=1)
        ttk.Label(form, text="Carpeta de la empresa", style="CardBold.TLabel").grid(row=0, column=0, sticky="w", padx=(0, px(10)), pady=px(5))
        ttk.Entry(form, textvariable=self.folder_var).grid(row=0, column=1, sticky="ew", pady=px(5))
        ttk.Button(form, text="Examinar…", command=self.choose_folder).grid(row=0, column=2, padx=(px(8), 0), pady=px(5))
        ttk.Label(form, text="Nombre corto", style="CardBold.TLabel").grid(row=1, column=0, sticky="w", padx=(0, px(10)), pady=px(5))
        ttk.Entry(form, textvariable=self.company_var, width=28).grid(row=1, column=1, sticky="w", pady=px(5))
        ttk.Label(form, text="Ejemplo: PRISMA", style="Muted.TLabel").grid(row=1, column=2, sticky="w", padx=(px(8), 0))
        actions = ttk.Frame(company.body, style="Card.TFrame"); actions.pack(fill="x", pady=(px(8), 0))
        self.analyze_btn = ttk.Button(actions, text="Analizar", style="Primary.TButton", command=self.analyze)
        self.analyze_btn.pack(side="left")
        self.rename_btn = ttk.Button(actions, text="Renombrar", command=self.rename, state="disabled")
        self.rename_btn.pack(side="left", padx=(px(8), 0))
        self.resolve_btn = ttk.Button(actions, text="Resolver archivo", command=self.open_conflict_manager, state="disabled")
        self.resolve_btn.pack(side="left", padx=(px(8), 0))
        ttk.Button(actions, text="Limpiar", command=self.clear_results).pack(side="right")
        ttk.Button(actions, text="Reiniciar", command=self.restart_app).pack(side="right", padx=(0, px(8)))
        ttk.Button(actions, text="Refrescar", command=self.refresh_app).pack(side="right", padx=(0, px(8)))

        # ---- métricas
        metrics = ttk.Frame(top, style="Bg.TFrame"); metrics.grid(row=1, column=0, sticky="ew", pady=(0, px(10)))
        defs = [("PDF analizados", "total", "neutral"), ("Por renombrar", "rename", "warn"), ("Correctos", "ok", "good"),
                ("Conflictos y duplicados", "conflict", "bad"), ("Omitidos o con error", "skipped", "neutral")]
        for i, (name, key, tone) in enumerate(defs):
            metrics.columnconfigure(i, weight=1, uniform="metric")
            card = MetricCard(metrics, L, name, tone)
            card.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else px(5), 0 if i == len(defs) - 1 else px(5)))
            self.metric_vars[key] = card.var

        # ---- acceso rápido SAT
        sat = Card(top, L)
        sat.grid(row=2, column=0, sticky="ew", pady=(0, px(10)))
        sat_row = ttk.Frame(sat.body, style="Card.TFrame"); sat_row.pack(fill="x"); sat_row.columnconfigure(0, weight=1)
        sat_left = ttk.Frame(sat_row, style="Card.TFrame"); sat_left.grid(row=0, column=0, sticky="ew")
        ttk.Label(sat_left, text="Acceso rápido SAT", style="CardTitle.TLabel").pack(anchor="w")
        status = ttk.Label(sat_left, textvariable=self.browser_status_var, style="Muted.TLabel", justify="left")
        status.pack(anchor="w", fill="x", pady=(px(2), 0)); autowrap(status, 6)
        sat_actions = ttk.Frame(sat_row, style="Card.TFrame"); sat_actions.grid(row=0, column=1, sticky="e", padx=(px(12), 0))
        self.sat_portal_btn = ttk.Button(sat_actions, text="Portal SAT", command=lambda: self.open_sat_browser(SAT_PORTAL_URL, "Portal SAT"), state="disabled")
        self.sat_portal_btn.pack(side="left", padx=(0, px(8)))
        self.sat_declarations_btn = ttk.Button(sat_actions, text="Declaraciones SAT", style="Primary.TButton", command=lambda: self.open_sat_browser(SAT_DECLARACIONES_URL, "Declaraciones SAT", declarations_workflow=True), state="disabled")
        self.sat_declarations_btn.pack(side="left", padx=(0, px(8)))
        self.sat_download_all_btn = ttk.Button(sat_actions, text="Descargar todas", command=self.request_download_all, state="disabled")
        self.sat_download_all_btn.pack(side="left")

        # ---- control de meses
        months = Card(top, L)
        months.grid(row=3, column=0, sticky="ew", pady=(0, px(4)))
        m_row = ttk.Frame(months.body, style="Card.TFrame"); m_row.pack(fill="x"); m_row.columnconfigure(0, weight=1)
        m_left = ttk.Frame(m_row, style="Card.TFrame"); m_left.grid(row=0, column=0, sticky="ew")
        ttk.Label(m_left, text="Control de meses", style="CardTitle.TLabel").pack(anchor="w")
        self.months_label = ttk.Label(m_left, textvariable=self.months_var, style="Card.TLabel", justify="left")
        self.months_label.pack(fill="x", pady=(px(3), 0)); autowrap(self.months_label, 6)
        ttk.Button(m_row, text="Ver detalle", command=self.show_months_popup).grid(row=0, column=1, padx=(px(12), 0), sticky="ne")

        # ---- revisión
        review = Card(self.panes, L, pad=(14, 12))
        rv = review.body; rv.columnconfigure(0, weight=1); rv.rowconfigure(1, weight=1)
        bar = ttk.Frame(rv, style="Card.TFrame"); bar.grid(row=0, column=0, sticky="ew", pady=(0, px(8))); bar.columnconfigure(0, weight=1)
        ttk.Label(bar, text="Revisión de PDF", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(bar, text="Mostrar", style="CardBold.TLabel").grid(row=0, column=1, padx=(0, px(8)))
        flt = L.combo(bar, textvariable=self.filter_var, state="readonly", values=FILTERS, width=16)
        flt.grid(row=0, column=2); flt.bind("<<ComboboxSelected>>", lambda e: self.refresh_tree())
        table = ttk.Frame(rv, style="Card.TFrame"); table.grid(row=1, column=0, sticky="nsew")
        table.rowconfigure(0, weight=1); table.columnconfigure(0, weight=1)
        cols = ("actual", "tipo", "mes", "ejercicio", "rfc", "estado", "nuevo")
        self.tree = ttk.Treeview(table, columns=cols, show="headings", selectmode="browse")
        headings = {"actual": "Archivo actual", "tipo": "Documento", "mes": "Mes", "ejercicio": "Ejercicio", "rfc": "RFC", "estado": "Estado", "nuevo": "Nombre final"}
        widths = {"actual": 245, "tipo": 150, "mes": 95, "ejercicio": 80, "rfc": 120, "estado": 115, "nuevo": 360}
        for c in cols:
            self.tree.heading(c, text=headings[c], command=lambda col=c: self.sort_tree(col, False))
            self.tree.column(c, width=px(widths[c]), minwidth=px(70), anchor="w")
        yscroll = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        xscroll = ttk.Scrollbar(table, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew"); yscroll.grid(row=0, column=1, sticky="ns"); xscroll.grid(row=1, column=0, sticky="ew")
        L.tag_tree(self.tree, TREE_TAGS)
        ttk.Label(rv, text="Detalle del archivo seleccionado", style="CardBold.TLabel").grid(row=2, column=0, sticky="w", pady=(px(10), px(2)))
        self.detail_label = ttk.Label(rv, textvariable=self.detail_var, style="Muted.TLabel", justify="left")
        self.detail_label.grid(row=3, column=0, sticky="ew"); autowrap(self.detail_label, 6)
        self.tree.bind("<<TreeviewSelect>>", self.show_selected_detail)
        self.tree.bind("<Double-1>", self.handle_double_click)
        self.panes.add(self.scroller, stretch="always", minsize=px(150))
        self.panes.add(review, stretch="always", minsize=px(240))

        self.progress = ttk.Progressbar(content, mode="determinate", maximum=100)
        self.progress.grid(row=1, column=0, sticky="ew", pady=(px(10), 0))

    def _place_sash(self):
        try:
            self.panes.sash_place(0, 0, max(self.look.px(170), self.panes.winfo_height() - self.look.px(330)))
        except tk.TclError:
            pass

    def _update_steps(self):
        ready = bool(self.folder_var.get().strip()) and bool(self.company_var.get().strip())
        analyzed = bool(self.infos)
        pending = any(i.status == "RENOMBRAR" for i in self.infos)
        self.shell.set_steps(["done" if ready else "active",
                              "pending" if not ready else ("done" if analyzed else "active"),
                              "pending" if not analyzed else ("active" if pending else "done")])

    def _update_metrics(self, counts=None):
        if counts is None:
            values = {k: "—" for k in self.metric_vars}
        else:
            values = {"total": len(self.infos), "rename": counts["RENOMBRAR"], "ok": counts["CORRECTO"],
                      "conflict": counts["CONFLICTO"] + counts["DUPLICADO"],
                      "skipped": counts["OMITIDO"] + counts["ERROR"] + counts["RFC DIFERENTE"]}
        for key, var in self.metric_vars.items():
            var.set(values[key])

    def show_help(self):
        show_help_dialog(self, self.look,
            how_to=["Elige la carpeta de la empresa y escribe su nombre corto (por ejemplo PRISMA).",
                    "Pulsa “Analizar”: se leen los PDF y se propone el nombre final de cada uno.",
                    "Revisa la tabla y el control de meses. Usa “Resolver archivo” para conflictos o duplicados.",
                    "Pulsa “Renombrar” para aplicar los nombres; nunca se sobrescribe un archivo existente.",
                    "Con la carpeta analizada puedes abrir el portal SAT y descargar declaraciones a esa carpeta."],
            shortcuts=list(COMMON_SHORTCUTS) + [("Doble clic", "Resolver el archivo o ver su detalle")],
            about="Organizador de documentos del SAT: analiza, renombra y clasifica declaraciones y acuses, con control mensual y descarga masiva.")

    def choose_folder(self):
        chosen = filedialog.askdirectory(title="Selecciona la carpeta de la empresa")
        if chosen:
            self.folder_var.set(chosen)
            self.summary_var.set("Carpeta seleccionada. Presiona ANALIZAR cuando estés listo.")

    def clear_results(self):
        self.infos = []
        for item in self.tree.get_children(): self.tree.delete(item)
        self.detail_var.set("Selecciona un PDF para ver sus detalles.")
        self.months_var.set("Analiza la carpeta para revisar qué meses están completos o pendientes.")
        self.months_data = {}
        self.company_start_date = None
        self.analyzed_folder = None
        self.rfc_var.set("RFC detectado: -")
        self._set_sat_buttons(False)
        self.browser_status_var.set("SAT: analiza una carpeta para habilitar accesos y fijar la ruta de descarga.")
        self.summary_var.set("Resultados limpiados. Puedes analizar nuevamente.")
        self.rename_btn.config(state="disabled")
        self.resolve_btn.config(state="disabled")
        self.progress["value"] = 0
        self._update_metrics()
        self._update_steps()

    def refresh_app(self):
        """Vuelve a analizar la carpeta actual sin cerrar la aplicación."""
        if not self.folder_var.get().strip():
            messagebox.showinfo(APP_TITLE, "Selecciona primero una carpeta para refrescar el análisis.")
            return
        self.clear_results()
        self.analyze()

    def restart_app(self):
        """Restablece la interfaz a su estado inicial sin cerrar el programa."""
        self.infos = []
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.folder_var.set("")
        self.company_var.set("")
        self.filter_var.set("TODOS")
        self.detail_var.set("Selecciona un PDF para ver sus detalles.")
        self.months_var.set("Analiza la carpeta para revisar qué meses están completos o pendientes.")
        self.months_data = {}
        self.company_start_date = None
        self.analyzed_folder = None
        self.rfc_var.set("RFC detectado: -")
        self._set_sat_buttons(False)
        self.browser_status_var.set("SAT: analiza una carpeta para habilitar accesos y fijar la ruta de descarga.")
        self.summary_var.set("Aplicación reiniciada. Selecciona una carpeta y escribe el nombre corto de la empresa.")
        self.rename_btn.config(state="disabled")
        self.resolve_btn.config(state="disabled")
        self.analyze_btn.config(state="normal")
        self.progress["value"] = 0
        self._update_metrics()
        self.refresh_tree()

    def analyze(self):
        folder = Path(self.folder_var.get().strip())
        company = sanitize_company_name(self.company_var.get())
        if not folder.is_dir():
            messagebox.showwarning(APP_TITLE, "Selecciona una carpeta válida.")
            return
        if not company:
            messagebox.showwarning(APP_TITLE, "Escribe el nombre corto de la empresa, por ejemplo: PRISMA.")
            return
        self.company_var.set(company)
        self.analyze_btn.config(state="disabled")
        self.rename_btn.config(state="disabled")
        self.progress["value"] = 15
        self.summary_var.set("Analizando PDFs…")
        self.update_idletasks()
        try:
            self.infos = analyze_folder(folder, company)
            self.progress["value"] = 100
        except Exception as exc:
            self.infos = []
            self.progress["value"] = 0
            self.refresh_tree()
            self.summary_var.set("El análisis se interrumpió. Usa REFRESCAR o REINICIAR APP para intentarlo de nuevo.")
            messagebox.showerror(APP_TITLE, f"Ocurrió un error durante el análisis:\n\n{exc}")
            return
        finally:
            self.analyze_btn.config(state="normal")

        counts = Counter(i.status for i in self.infos)
        candidates = [i.rfc for i in self.infos if i.rfc and i.status not in {"ERROR", "OMITIDO", "RFC DIFERENTE"}]
        primary = Counter(candidates).most_common(1)[0][0] if candidates else "-"
        self.rfc_var.set(f"RFC detectado: {primary}")
        years_for_rfc = [int(i.year) for i in self.infos if i.year and str(i.year).isdigit()]
        self.company_start_date = rfc_company_start_date(primary if primary != "-" else None, years_for_rfc)
        self.months_data = compute_month_completeness(self.infos, primary if primary != "-" else None)
        self.update_months_summary()
        self.analyzed_folder = folder.resolve()
        self._set_sat_buttons(True)
        self.browser_status_var.set(f"Descargas SAT → {self.analyzed_folder}")
        self.summary_var.set(
            f"PDF: {len(self.infos)}  |  Para renombrar: {counts['RENOMBRAR']}  |  Correctos: {counts['CORRECTO']}  |  "
            f"RESICO: {sum(1 for i in self.infos if i.is_resico)}  |  Duplicados: {counts['DUPLICADO']}  |  Conflictos: {counts['CONFLICTO']}  |  "
            f"Omitidos/errores: {counts['OMITIDO']+counts['ERROR']+counts['RFC DIFERENTE']}"
        )
        self.rename_btn.config(state="normal" if counts["RENOMBRAR"] else "disabled")
        self._update_metrics(counts)
        self.refresh_tree()

    def update_months_summary(self):
        if not self.months_data:
            self.months_var.set("No se detectaron periodos válidos para evaluar los meses.")
            return

        lines = []
        ordered_months = sorted(MONTH_NUMBERS, key=MONTH_NUMBERS.get)
        for year, data in sorted(self.months_data.items(), reverse=True):
            complete = []
            pending = []
            before_start = []
            not_due = []
            for month in ordered_months:
                item = data[month]
                if not item.get("aplicable", True):
                    reason = item.get("razon_no_aplica")
                    if reason == "NO_EXIGIBLE":
                        not_due.append(month)
                    else:
                        before_start.append(month)
                    continue
                d = bool(item["declaracion"])
                a = bool(item["acuse"])
                if d and a:
                    complete.append(month)
                else:
                    missing = []
                    if not d: missing.append("declaración")
                    if not a: missing.append("acuse")
                    pending.append(f"{month} (falta {' y '.join(missing)})")
            ctext = ", ".join(complete) if complete else "ninguno"
            ptext = ", ".join(pending) if pending else "ninguno"
            line = f"{year}  |  Completos: {ctext}\nPendientes: {ptext}"
            if before_start:
                line += f"\nNo aplican por fecha de alta: {', '.join(before_start)}"
            if not_due:
                line += f"\nNo exigibles aún (se presentan el mes siguiente): {', '.join(not_due)}"
            lines.append(line)
        self.months_var.set("\n".join(lines))

    def show_months_popup(self):
        if not self.months_data:
            messagebox.showinfo("Control de meses", "Primero analiza una carpeta con declaraciones SAT.")
            return
        L = self.look; px = L.px
        win = Dialog(self, L, "Control de meses", size=(1120, 760), minsize=(860, 620),
                     subtitle="Un mes está completo con al menos una DECLARACIÓN normal y un ACUSE normal. "
                              "Las complementarias no cuentan. El mes actual se evalúa hasta el mes siguiente.")
        foot = win.footer()
        ttk.Button(foot, text="Cerrar", command=win.close, style="Primary.TButton").pack(side="right")
        ttk.Label(foot, text="Solo los PDF descargados desde la sesión SAT se conservarán en la carpeta de empresa analizada.",
                  style="MutedBg.TLabel").pack(side="left")
        top = ttk.Frame(win.outer, style="Bg.TFrame"); top.pack(fill="x", pady=(0, px(12)))
        info = Card(top, L, pad=(18, 12)); info.pack(side="left", fill="x", expand=True)
        rfc_text = self.rfc_var.get().replace("RFC detectado: ", "")
        start_text = self.company_start_date.strftime("%d/%m/%Y") if self.company_start_date else "No determinada"
        ttk.Label(info.body, text=f"Empresa: {self.company_var.get()}    |    RFC: {rfc_text}", style="CardTitle.TLabel").pack(anchor="w")
        detail = ttk.Label(info.body, text=f"Fecha de alta considerada: {start_text}    |    Descargas: {self.analyzed_folder or '-'}",
                           style="Muted.TLabel", justify="left")
        detail.pack(anchor="w", fill="x", pady=(px(4), 0)); autowrap(detail, 6)
        buttons = ttk.Frame(top, style="Bg.TFrame"); buttons.pack(side="right", padx=(px(12), 0))
        ttk.Button(buttons, text="Portal SAT", command=lambda: self.open_sat_browser(SAT_PORTAL_URL, "Portal SAT")).pack(side="left", padx=(0, px(8)))
        ttk.Button(buttons, text="Declaraciones SAT", style="Primary.TButton",
                   command=lambda: self.open_sat_browser(SAT_DECLARACIONES_URL, "Declaraciones SAT", declarations_workflow=True)).pack(side="left")
        notebook = ttk.Notebook(win.outer)
        notebook.pack(fill="both", expand=True)
        ordered_months = sorted(MONTH_NUMBERS, key=MONTH_NUMBERS.get)
        for year, data in sorted(self.months_data.items(), reverse=True):
            page = ttk.Frame(notebook, style="Bg.TFrame", padding=px(14))
            notebook.add(page, text=f"  {year}  ")
            for col in range(3): page.grid_columnconfigure(col, weight=1, uniform="months")
            for row in range(4): page.grid_rowconfigure(row, weight=1, uniform="monthsrows")
            for idx, month in enumerate(ordered_months):
                item = data[month]
                applicable = item.get("aplicable", True)
                d, a = item["declaracion"], item["acuse"]
                if not applicable:
                    bg, fg, icon = "neutral_bg", "muted", "—"
                    if item.get("razon_no_aplica") == "NO_EXIGIBLE":
                        state_text, detail_text = "NO EXIGIBLE AÚN", "Se presenta y evalúa el mes siguiente"
                    else:
                        state_text, detail_text = "NO APLICA", "Anterior a la fecha de alta"
                elif d and a:
                    bg, fg, icon, state_text, detail_text = "success_bg", "success", "✓", "COMPLETO", "Declaración ✓    Acuse ✓"
                else:
                    bg, fg, icon, state_text = "warn_bg", "warn", "⚠", "INCOMPLETO"
                    missing = [name for name, ok in (("DECLARACIÓN", d), ("ACUSE", a)) if not ok]
                    detail_text = "Falta: " + " y ".join(missing)
                tile = tk.Frame(page, bd=0, highlightthickness=1, padx=px(14), pady=px(12))
                L.track(tile, bg=bg, highlightbackground=fg, highlightcolor=fg)
                tile.grid(row=idx // 3, column=idx % 3, sticky="nsew", padx=px(7), pady=px(7))
                for text, size, bold, pad in ((f"{MONTH_NUMBERS[month]}. {month}", 14, True, 0), (f"{icon}  {state_text}", 13, True, px(4)), (detail_text, 10, False, 0)):
                    lab = tk.Label(tile, text=text, bd=0, anchor="w", justify="left")
                    L.track(lab, bg=bg, fg=fg, font=lambda k, s=size, b=bold: k.font(s, b))
                    lab.pack(anchor="w", pady=(pad, 0))
                if applicable and not (d and a):
                    ttk.Button(tile, text="Descargar en SAT", command=lambda m=month, y=year: self.open_sat_browser(
                        SAT_DECLARACIONES_URL, f"Declaraciones SAT · {m} {y}", declarations_workflow=True)).pack(anchor="e", pady=(px(8), 0))
        win.show()

    def _set_sat_buttons(self, enabled: bool):
        state = "normal" if enabled and not self.browser_running else "disabled"
        if hasattr(self, "sat_portal_btn"):
            self.sat_portal_btn.config(state=state)
        if hasattr(self, "sat_declarations_btn"):
            self.sat_declarations_btn.config(state=state)
        if hasattr(self, "sat_download_all_btn"):
            bulk_state = (
                "normal"
                if enabled and self.browser_running and self.browser_declarations_mode and not self.bulk_download_running
                else "disabled"
            )
            self.sat_download_all_btn.config(state=bulk_state)

    def request_download_all(self):
        """Solicita al hilo del navegador descargar todos los PDF visibles de la consulta SAT."""
        if not self.browser_running or not self.browser_declarations_mode:
            messagebox.showinfo(APP_TITLE, "Abre primero DECLARACIONES SAT y entra a la pantalla de consulta.")
            return
        if self.bulk_download_running:
            return
        self.bulk_download_running = True
        self._set_sat_buttons(bool(self.analyzed_folder))
        self.browser_status_var.set("SAT: buscando declaraciones en la tabla para descargar todos los PDF…")
        self.browser_command_queue.put(("download_all",))

    def _on_folder_changed(self, *_):
        if not self.analyzed_folder:
            return
        raw = self.folder_var.get().strip()
        try:
            current = Path(raw).resolve() if raw else None
        except Exception:
            current = None
        if current != self.analyzed_folder:
            self._set_sat_buttons(False)
            self.browser_status_var.set("SAT deshabilitado: la carpeta cambió. Presiona ANALIZAR para fijar la nueva ruta de descarga.")

    def open_sat_browser(self, url: str, label: str, declarations_workflow: bool = False):
        if not self.analyzed_folder or not self.analyzed_folder.is_dir():
            messagebox.showwarning(APP_TITLE, "Primero analiza la carpeta de la empresa para fijar la ruta de descarga.")
            return
        try:
            current = Path(self.folder_var.get().strip()).resolve()
        except Exception:
            current = None
        if current != self.analyzed_folder:
            messagebox.showwarning(APP_TITLE, "La carpeta cambió desde el último análisis. Vuelve a presionar ANALIZAR antes de abrir el SAT.")
            self._set_sat_buttons(False)
            return
        if self.browser_running:
            messagebox.showinfo(APP_TITLE, "Ya hay una sesión SAT abierta. Cierra esa ventana antes de iniciar otra.")
            return

        if not playwright_firefox_present():
            messagebox.showerror(
                APP_TITLE,
                "Firefox para el módulo SAT no está instalado en la ruta esperada.\n\n"
                f"Ruta esperada:\n{PLAYWRIGHT_BROWSER_DIR}\n\n"
                "Ejecuta INSTALAR_FIREFOX_SAT_v26.bat o vuelve a ejecutar CREAR_EXE_v26.bat."
            )
            return

        while True:
            try:
                self.browser_command_queue.get_nowait()
            except queue.Empty:
                break
        self.browser_running = True
        self.browser_declarations_mode = declarations_workflow
        self.bulk_download_running = False
        self._set_sat_buttons(True)
        self.browser_status_var.set(f"Abriendo {label} · Descargas → {self.analyzed_folder}")
        threading.Thread(target=self._run_sat_browser, args=(url, label, self.analyzed_folder, declarations_workflow), daemon=True).start()

    def _run_sat_browser(self, url: str, label: str, download_folder: Path, declarations_workflow: bool = False):
        error = None
        saved_count = 0
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p, tempfile.TemporaryDirectory(prefix="OrganizadorSAT_Downloads_") as temp_download_dir:
                # Firefox descarga primero en una carpeta temporal interna. La
                # carpeta de la empresa recibe únicamente PDFs validados.
                browser = p.firefox.launch(
                    headless=False,
                    downloads_path=temp_download_dir,
                    firefox_user_prefs={
                        "pdfjs.disabled": True,
                        "browser.download.useDownloadDir": True,
                        "browser.download.folderList": 2,
                        "browser.download.dir": temp_download_dir,
                        "browser.download.manager.showWhenStarting": False,
                        "browser.helperApps.alwaysAsk.force": False,
                        "browser.helperApps.neverAsk.saveToDisk": "application/pdf,application/octet-stream",
                    },
                )
                context = browser.new_context(accept_downloads=True)

                # La página puede pedir una descarga masiva desde un botón flotante
                # inyectado por el Organizador. La función expuesta solo encola la
                # orden; el trabajo real se ejecuta en este mismo hilo de Playwright.
                try:
                    context.expose_function(
                        "organizadorDescargarTodas",
                        lambda: None if self.bulk_download_running else self.browser_command_queue.put(("download_all",)),
                    )
                except Exception:
                    pass

                def attach_download_handler(page):
                    def on_download(download):
                        nonlocal saved_count
                        try:
                            # Espera a que Playwright complete el archivo temporal.
                            temp_path_raw = download.path()
                            if not temp_path_raw:
                                return
                            temp_path = Path(temp_path_raw)
                            try:
                                with temp_path.open("rb") as fh:
                                    is_pdf = fh.read(5) == b"%PDF-"
                            except Exception:
                                is_pdf = False

                            # Solo los PDF pasan a la carpeta de la empresa.
                            if not is_pdf:
                                return

                            suggested = Path(download.suggested_filename).name or "declaracion.pdf"
                            if Path(suggested).suffix.lower() != ".pdf":
                                suggested = suggested + ".pdf"
                            target = unique_download_path(download_folder, suggested)
                            download.save_as(str(target))
                            saved_count += 1
                        except Exception:
                            pass
                    page.on("download", on_download)

                page = context.new_page()
                attach_download_handler(page)
                context.on("page", lambda new_page: attach_download_handler(new_page) if new_page is not page else None)
                page.goto(url, wait_until="domcontentloaded", timeout=90000)

                # El SAT no siempre permite entrar directamente al login de declaraciones:
                # necesita que la navegación nazca desde el portal de Personas Morales.
                # Para el botón DECLARACIONES SAT abrimos esa página y hacemos clic en
                # "Pagos provisionales del ISR" como lo haría el usuario.
                if declarations_workflow:
                    # Flujo correcto del portal SAT:
                    # 1) Abrir Régimen General de Ley.
                    # 2) Desplegar la pestaña 5 "Declara".
                    # 3) Entrar a "Pagos provisionales del ISR" desde ese panel.
                    # Entrar directo al login puede devolver una página en blanco.
                    declara_opened = False
                    clicked = False

                    # Intento principal: texto visible "Declara".
                    try:
                        declara = page.get_by_text("Declara", exact=True).first
                        declara.wait_for(state="visible", timeout=20000)
                        declara.click(timeout=20000)
                        declara_opened = True
                    except Exception:
                        pass

                    # Respaldo 1: cualquier control clicable que contenga "Declara".
                    if not declara_opened:
                        try:
                            declara = page.locator(
                                "button, a, [role='button'], [role='tab'], div",
                                has_text=re.compile(r"^\s*Declara\s*$", re.IGNORECASE),
                            ).first
                            declara.wait_for(state="visible", timeout=10000)
                            declara.click(timeout=10000)
                            declara_opened = True
                        except Exception:
                            pass

                    # Respaldo 2: bloque/pestaña 5 que además contenga la palabra Declara.
                    if not declara_opened:
                        try:
                            candidates = page.locator("a, button, [role='button'], [role='tab'], div")
                            count = min(candidates.count(), 300)
                            for idx in range(count):
                                c = candidates.nth(idx)
                                try:
                                    txt = re.sub(r"\s+", " ", c.inner_text(timeout=500)).strip()
                                except Exception:
                                    continue
                                if re.search(r"(?:^|\s)5(?:\s|$)", txt) and re.search(r"Declara", txt, re.IGNORECASE):
                                    try:
                                        c.click(timeout=5000)
                                        declara_opened = True
                                        break
                                    except Exception:
                                        continue
                        except Exception:
                            pass

                    if declara_opened:
                        try:
                            page.wait_for_timeout(700)
                        except Exception:
                            pass

                    # Ya desplegada la pestaña, buscar el enlace de pagos provisionales.
                    try:
                        link = page.get_by_role(
                            "link",
                            name=re.compile(r"Pagos\s+provisionales\s+del\s+ISR", re.IGNORECASE),
                        ).first
                        link.wait_for(state="visible", timeout=20000)
                        link.click(timeout=20000)
                        clicked = True
                    except Exception:
                        # Respaldo para cambios menores en el HTML del portal.
                        try:
                            link = page.locator(
                                "a",
                                has_text=re.compile(r"Pagos\s+provisionales\s+del\s+ISR", re.IGNORECASE),
                            ).first
                            link.wait_for(state="visible", timeout=10000)
                            link.click(timeout=10000)
                            clicked = True
                        except Exception:
                            clicked = False

                    # Nunca forzamos el URL del login. Si el portal cambia, dejamos
                    # la página de Régimen General abierta para continuar manualmente.
                    if clicked:
                        try:
                            page.wait_for_timeout(1200)
                        except Exception:
                            pass

                def find_consulta_page():
                    """Localiza la pantalla que contiene la tabla de declaraciones."""
                    for candidate in reversed(context.pages):
                        try:
                            url_now = (candidate.url or "").lower()
                            if "consulta/consulta" in url_now or "pstdcypisr" in url_now:
                                if candidate.locator("table").count() > 0:
                                    return candidate
                            body_text = candidate.locator("body").inner_text(timeout=800)
                            normalized = norm(body_text)
                            if "NO. DE OPERACION" in normalized and "TIPO DE DECLARACION" in normalized:
                                return candidate
                        except Exception:
                            continue
                    return None

                def inject_bulk_button(candidate):
                    """Agrega un botón flotante a la página SAT sin modificar datos del portal."""
                    try:
                        candidate.evaluate("""
                            () => {
                                if (document.getElementById('organizador-sat-descargar-todas')) return;
                                const b = document.createElement('button');
                                b.id = 'organizador-sat-descargar-todas';
                                b.type = 'button';
                                b.textContent = '⬇ DESCARGAR TODAS';
                                Object.assign(b.style, {
                                    position: 'fixed', right: '24px', bottom: '24px', zIndex: '2147483647',
                                    background: '#b31f47', color: 'white', border: '0', borderRadius: '7px',
                                    padding: '13px 18px', font: '700 14px Arial, sans-serif', cursor: 'pointer',
                                    boxShadow: '0 4px 14px rgba(0,0,0,.28)'
                                });
                                b.title = 'Descarga en cola todos los PDF de la tabla visible';
                                b.addEventListener('click', async () => {
                                    if (b.dataset.busy === '1') return;
                                    b.dataset.busy = '1';
                                    const original = b.textContent;
                                    b.textContent = '⏳ SOLICITANDO…';
                                    b.disabled = true;
                                    try {
                                        await window.organizadorDescargarTodas();
                                    } catch (e) {
                                        console.error(e);
                                    }
                                    setTimeout(() => {
                                        b.textContent = original;
                                        b.disabled = false;
                                        b.dataset.busy = '0';
                                    }, 1800);
                                });
                                document.body.appendChild(b);
                            }
                        """)
                    except Exception:
                        pass

                def find_pdf_control(row):
                    """Encuentra el control PDF de una fila tolerando cambios menores del HTML SAT."""
                    selectors = (
                        "a:has(img[src*='pdf' i])",
                        "a:has(img[alt*='pdf' i])",
                        "a:has(img[title*='pdf' i])",
                        "button:has(img[src*='pdf' i])",
                        "button:has(img[alt*='pdf' i])",
                        "input[type='image'][src*='pdf' i]",
                        "a[title*='pdf' i]",
                        "a[aria-label*='pdf' i]",
                        "button[title*='pdf' i]",
                    )
                    for selector in selectors:
                        try:
                            loc = row.locator(selector)
                            if loc.count() > 0:
                                return loc.first
                        except Exception:
                            continue
                    # En la consulta actual del SAT el icono PDF vive en la primera celda.
                    try:
                        first_cell = row.locator("td").first
                        controls = first_cell.locator("a, button, input[type='image'], [role='button']")
                        if controls.count() > 0:
                            return controls.first
                    except Exception:
                        pass
                    return None

                def bulk_download_all():
                    nonlocal saved_count
                    candidate = find_consulta_page()
                    if candidate is None:
                        self.browser_event_queue.put((
                            "bulk_error",
                            "No encontré la tabla de declaraciones. Entra a Consulta de declaraciones y vuelve a pulsar DESCARGAR TODAS.",
                        ))
                        return

                    try:
                        rows = candidate.locator("table tbody tr")
                        row_count = rows.count()
                    except Exception:
                        row_count = 0
                    if row_count == 0:
                        try:
                            rows = candidate.locator("table tr")
                            row_count = rows.count()
                        except Exception:
                            row_count = 0

                    entries = []
                    for idx in range(row_count):
                        row = rows.nth(idx)
                        try:
                            cells = row.locator("td")
                            if cells.count() < 2:
                                continue
                            texts = [re.sub(r"\s+", " ", cells.nth(j).inner_text(timeout=800)).strip() for j in range(cells.count())]
                            operation = next((t for t in texts if re.fullmatch(r"\d{8,}", t.replace(" ", ""))), "")
                            control = find_pdf_control(row)
                            if control is None:
                                continue
                            period = texts[6] if len(texts) > 6 else ""
                            dtype = texts[2] if len(texts) > 2 else ""
                            entries.append((idx, operation, period, dtype))
                        except Exception:
                            continue

                    total = len(entries)
                    if not total:
                        self.browser_event_queue.put((
                            "bulk_error",
                            "La tabla apareció, pero no pude identificar botones PDF descargables. No se hizo ningún clic.",
                        ))
                        return

                    start_saved = saved_count
                    failed = 0
                    self.browser_event_queue.put(("bulk_start", total))

                    for pos, (row_idx, operation, period, dtype) in enumerate(entries, start=1):
                        if not browser.is_connected():
                            failed += total - pos + 1
                            break
                        try:
                            current_rows = candidate.locator("table tbody tr")
                            if current_rows.count() <= row_idx:
                                current_rows = candidate.locator("table tr")
                            row = current_rows.nth(row_idx)
                            control = find_pdf_control(row)
                            if control is None:
                                raise RuntimeError("No se encontró el icono PDF")

                            before = saved_count
                            control.scroll_into_view_if_needed(timeout=5000)
                            control.click(timeout=10000)

                            # Espera a que el manejador general valide y copie el PDF.
                            deadline = time.time() + 25
                            while time.time() < deadline and browser.is_connected():
                                if saved_count > before:
                                    break
                                candidate.wait_for_timeout(250)
                            if saved_count <= before:
                                failed += 1
                        except Exception:
                            failed += 1

                        bulk_saved = saved_count - start_saved
                        label_bits = [x for x in (period, dtype, operation) if x]
                        label_row = " · ".join(label_bits) if label_bits else f"fila {pos}"
                        self.browser_event_queue.put(("bulk_progress", pos, total, bulk_saved, failed, label_row))
                        try:
                            candidate.wait_for_timeout(350)
                        except Exception:
                            pass

                    self.browser_event_queue.put(("bulk_done", total, saved_count - start_saved, failed))

                while browser.is_connected():
                    pages = context.pages
                    if not pages:
                        browser.close()
                        break

                    # Si el usuario ya llegó a la consulta, mostramos el botón dentro del SAT.
                    if declarations_workflow:
                        consulta_page = find_consulta_page()
                        if consulta_page is not None:
                            inject_bulk_button(consulta_page)

                    try:
                        command = self.browser_command_queue.get_nowait()
                    except queue.Empty:
                        command = None
                    if command and command[0] == "download_all":
                        bulk_download_all()

                    try:
                        pages[0].wait_for_timeout(500)
                    except Exception:
                        break
        except Exception as exc:
            error = str(exc)
        self.browser_result_queue.put((label, saved_count, error))

    def _poll_browser_results(self):
        try:
            while True:
                event = self.browser_event_queue.get_nowait()
                kind = event[0]
                if kind == "bulk_start":
                    total = event[1]
                    self.bulk_download_running = True
                    self.progress["maximum"] = max(1, total)
                    self.progress["value"] = 0
                    self.browser_status_var.set(f"SAT: descargando 0 / {total} declaraciones…")
                    self._set_sat_buttons(bool(self.analyzed_folder))
                elif kind == "bulk_progress":
                    pos, total, saved, failed, row_label = event[1:]
                    self.progress["maximum"] = max(1, total)
                    self.progress["value"] = pos
                    self.browser_status_var.set(
                        f"SAT: {pos}/{total} procesadas · {saved} PDF guardados · {failed} error(es) · {row_label}"
                    )
                elif kind == "bulk_done":
                    total, saved, failed = event[1:]
                    self.bulk_download_running = False
                    self.progress["maximum"] = 100
                    self.progress["value"] = 100
                    self._set_sat_buttons(bool(self.analyzed_folder))
                    self.browser_status_var.set(
                        f"SAT: descarga masiva terminada · {saved}/{total} PDF guardados · {failed} error(es)."
                    )
                    messagebox.showinfo(
                        "Descarga de declaraciones SAT",
                        f"Proceso terminado.\n\nDeclaraciones detectadas: {total}\nPDF guardados: {saved}\nErrores: {failed}\n\n"
                        "Los PDF quedaron en la carpeta activa de la empresa. Al cerrar Firefox se reanalizarán automáticamente."
                    )
                elif kind == "bulk_error":
                    self.bulk_download_running = False
                    self.progress["maximum"] = 100
                    self.progress["value"] = 0
                    self._set_sat_buttons(bool(self.analyzed_folder))
                    self.browser_status_var.set(f"SAT: {event[1]}")
                    messagebox.showwarning("Descarga de declaraciones SAT", event[1])
        except queue.Empty:
            pass

        try:
            while True:
                label, saved_count, error = self.browser_result_queue.get_nowait()
                self._sat_browser_finished(label, saved_count, error)
        except queue.Empty:
            pass
        self.after(300, self._poll_browser_results)

    def _sat_browser_finished(self, label: str, saved_count: int, error: Optional[str]):
        self.browser_running = False
        self.browser_declarations_mode = False
        self.bulk_download_running = False
        if error:
            self.browser_status_var.set("No se pudo iniciar la sesión SAT.")
            self._set_sat_buttons(bool(self.analyzed_folder))
            messagebox.showerror(
                APP_TITLE,
                "No fue posible iniciar Firefox para el SAT.\n\n"
                f"Detalle: {error}\n\n"
                f"Ruta de navegador configurada:\n{PLAYWRIGHT_BROWSER_DIR}\n\n"
                "Ejecuta INSTALAR_FIREFOX_SAT_v26.bat o vuelve a ejecutar CREAR_EXE_v26.bat."
            )
            return

        self.browser_status_var.set(f"Sesión {label} cerrada · {saved_count} descarga(s) guardada(s). Reanalizando carpeta…")
        if self.analyzed_folder and self.analyzed_folder.is_dir():
            self.after(150, self.analyze)
        else:
            self._set_sat_buttons(False)

    def filtered_indexes(self):
        filt = self.filter_var.get()
        for idx, i in enumerate(self.infos):
            if (
                filt == "TODOS"
                or (filt == "RESICO" and i.is_resico)
                or (filt == "SALARIOS" and i.is_salarios)
                or i.status == filt
                or (filt == "OMITIDO/ERROR" and i.status in {"OMITIDO", "ERROR", "RFC DIFERENTE"})
            ):
                yield idx, i

    def refresh_tree(self):
        for item in self.tree.get_children(): self.tree.delete(item)
        for idx, i in self.filtered_indexes():
            dtype = i.document_kind or "-"
            if i.document_kind == "DECLARACION" and i.declaration_type:
                dtype = "DECL. " + norm(i.declaration_type)
            elif i.document_kind == "ACUSE" and i.declaration_type:
                dtype = "ACUSE " + norm(i.declaration_type)
            row_tags = ("RESICO",) if (i.is_resico or i.is_salarios) else (i.status,)
            self.tree.insert("", "end", iid=str(idx), values=(i.path.name, dtype, i.month or "-", i.year or "-", i.rfc or "-", i.status, i.expected_name or "-"), tags=row_tags)
        self._update_steps()

    def sort_tree(self, col, reverse):
        items = [(self.tree.set(k, col).casefold(), k) for k in self.tree.get_children("")]
        items.sort(reverse=reverse)
        for index, (_, k) in enumerate(items): self.tree.move(k, "", index)
        self.tree.heading(col, command=lambda: self.sort_tree(col, not reverse))

    def rename(self):
        pending = [i for i in self.infos if i.status == "RENOMBRAR"]
        if not pending:
            messagebox.showinfo(APP_TITLE, "No hay archivos pendientes de renombrar.")
            return
        preview = "\n".join(f"• {i.path.name}\n  → {i.expected_name}" for i in pending[:5])
        if len(pending) > 5: preview += f"\n\n… y {len(pending)-5} archivo(s) más."
        if not messagebox.askyesno(APP_TITLE, f"Se renombrarán {len(pending)} archivo(s).\n\n{preview}\n\nNo se sobrescribirá ningún archivo existente.\n\n¿Continuar?"):
            return
        self.progress["value"] = 30
        self.update_idletasks()
        count, errors = execute_renames(self.infos)
        self.progress["value"] = 100
        if errors:
            messagebox.showerror(APP_TITLE, "No se completó el proceso:\n\n" + "\n".join(errors[:8]))
        else:
            messagebox.showinfo(APP_TITLE, f"Proceso terminado.\n\nArchivos renombrados: {count}")
        self.analyze()

    def detail_text(self, info: PdfInfo) -> str:
        return (
            f"Archivo: {info.path.name}    |    Estado: {info.status}\n"
            f"Documento: {info.document_kind or '-'}    |    Tipo: {info.declaration_type or '-'}    |    RESICO: {'Sí' if info.is_resico else 'No'}    |    SALARIOS: {'Sí' if info.is_salarios else 'No'}    |    "
            f"Periodo: {info.month or '-'} {info.year or '-'}    |    RFC: {info.rfc or '-'}\n"
            f"Nombre final: {info.expected_name or '-'}\n"
            f"Detalle: {info.detail}"
        )

    def show_selected_detail(self, _event=None):
        selected = self.tree.selection()
        if not selected:
            self.resolve_btn.config(state="disabled")
            return
        info = self.infos[int(selected[0])]
        self.detail_var.set(self.detail_text(info))
        # El gestor manual sirve especialmente para conflictos, duplicados y
        # omitidos, pero también puede corregir una clasificación dudosa antes
        # de renombrar. Los archivos ya correctos se dejan fuera por seguridad.
        self.resolve_btn.config(state="disabled" if info.status == "CORRECTO" else "normal")

    def handle_double_click(self, _event=None):
        selected = self.tree.selection()
        if not selected:
            return
        info = self.infos[int(selected[0])]
        if info.status in {"CONFLICTO", "DUPLICADO", "OMITIDO", "ERROR", "RFC DIFERENTE"}:
            self.open_conflict_manager()
        else:
            self.show_detail_popup()

    def _open_pdf_external(self, path: Path):
        """Abre el PDF con el visor predeterminado del sistema operativo."""
        try:
            if sys.platform.startswith("win"):
                os.startfile(str(path))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception as exc:
            messagebox.showerror(APP_TITLE, f"No se pudo abrir la vista previa del PDF:\n\n{exc}")

    def _next_duplicate_name(self, info: PdfInfo) -> Optional[str]:
        """Obtiene el siguiente nombre libre agregando 2, 3, 4... al final."""
        if not info.expected_name:
            return None
        # Si el nombre calculado ya trae un consecutivo final, se toma como
        # base el nombre sin ese consecutivo para continuar la secuencia.
        base = Path(info.expected_name)
        stem = re.sub(r"\s+(\d+)$", "", base.stem).strip()
        base_name = f"{stem}{base.suffix or '.pdf'}"
        folder = info.path.parent
        reserved = {
            j.expected_name.casefold()
            for j in self.infos
            if j is not info and j.expected_name and j.status in {"RENOMBRAR", "CORRECTO"}
        }
        # El nombre base puede ser válido si no está ocupado por otro archivo.
        base_path = folder / base_name
        if (not base_path.exists() or base_path.resolve() == info.path.resolve()) and base_name.casefold() not in reserved:
            return base_name
        n = 2
        while n < 10000:
            candidate = add_duplicate_suffix(base_name, n)
            cpath = folder / candidate
            if (not cpath.exists() or cpath.resolve() == info.path.resolve()) and candidate.casefold() not in reserved:
                return candidate
            n += 1
        return None

    def _manual_name_for_type(self, info: PdfInfo, choice: str) -> Optional[str]:
        """Construye el nombre estándar al elegir manualmente el tipo."""
        if not info.month:
            return None
        month_number = MONTH_NUMBERS.get(info.month)
        if not month_number:
            return None
        company = sanitize_company_name(self.company_var.get())
        if not company:
            return None

        choices = {
            "DECLARACION NORMAL": ("DECLARACION", "Normal", 0, "DECLARACION ISR E IVA"),
            "DECLARACION COMPLEMENTARIA": ("DECLARACION", "Complementaria", 1, "DECLARACION COMPLEMENTARIA ISR E IVA"),
            "ACUSE NORMAL": ("ACUSE", "Normal", 2, "ACUSE ISR E IVA"),
            "ACUSE COMPLEMENTARIA": ("ACUSE", "Complementaria", 3, "ACUSE COMPLEMENTARIA ISR E IVA"),
        }
        data = choices.get(choice)
        if not data:
            return None
        kind, dtype, suffix, label = data
        info.document_kind = kind
        info.declaration_type = dtype

        # RESICO/SALARIOS conservan su carácter especial y usan el siguiente
        # decimal libre del mes para no competir con los documentos ordinarios.
        tags = []
        if info.is_resico:
            tags.append("RESICO")
        if info.is_salarios:
            tags.append("SALARIOS")
        if tags:
            used_suffixes = set()
            pat = re.compile(rf"^{month_number}\.(\d+)\.-\s", re.IGNORECASE)
            for j in self.infos:
                if j is info or j.month != info.month or not j.expected_name:
                    continue
                m = pat.match(j.expected_name)
                if m:
                    used_suffixes.add(int(m.group(1)))
                elif j.expected_name.upper().startswith(f"{month_number}.-"):
                    used_suffixes.add(0)
            dynamic = 1
            while dynamic in used_suffixes:
                dynamic += 1
            tag_text = " " + " ".join(tags)
            extra = f" {info.complement_sequence}" if dtype.upper() == "COMPLEMENTARIA" and info.complement_sequence else ""
            return f"{month_number}.{dynamic}.- {label} {info.month} {company}{tag_text}{extra}.pdf"

        if suffix == 0:
            return f"{month_number}.- {label} {info.month} {company}.pdf"
        extra = f" {info.complement_sequence}" if dtype.upper() == "COMPLEMENTARIA" and info.complement_sequence else ""
        return f"{month_number}.{suffix}.- {label} {info.month} {company}{extra}.pdf"

    def open_conflict_manager(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo(APP_TITLE, "Selecciona primero un archivo de la tabla.")
            return
        idx = int(selected[0])
        info = self.infos[idx]
        if info.status == "CORRECTO":
            messagebox.showinfo(APP_TITLE, "El archivo seleccionado ya está correcto.")
            return
        L = self.look; px = L.px
        win = Dialog(self, L, "Resolver archivo", size=(760, 700), minsize=(660, 560), modal=True,
                     subtitle="Revisa el PDF y decide cómo debe tratarse. Los cambios se aplican al plan; "
                              "el archivo no se renombra hasta pulsar RENOMBRAR.")
        foot = win.footer()
        ttk.Button(foot, text="Cerrar", command=win.close).pack(side="right")

        info_card = Card(win.outer, L, "Archivo seleccionado")
        info_card.pack(fill="x")
        info_text = tk.StringVar(value=self.detail_text(info))
        lab = ttk.Label(info_card.body, textvariable=info_text, style="Card.TLabel", justify="left")
        lab.pack(anchor="w", fill="x"); autowrap(lab, 6)
        preview_row = ttk.Frame(win.outer, style="Bg.TFrame"); preview_row.pack(fill="x", pady=(px(10), px(10)))
        ttk.Button(preview_row, text="Vista previa del PDF", command=lambda: self._open_pdf_external(info.path)).pack(side="left")
        ttk.Button(preview_row, text="Ver detalle completo", command=self.show_detail_popup).pack(side="left", padx=(px(8), 0))

        # Acción 1: resolver como duplicado/consecutivo.
        dup_card = Card(win.outer, L, "Si es otra copia válida del mismo tipo")
        dup_card.pack(fill="x", pady=(0, px(10)))
        dup_preview = tk.StringVar(value="")
        lab = ttk.Label(dup_card.body, textvariable=dup_preview, style="Muted.TLabel", justify="left")
        lab.pack(anchor="w", fill="x", pady=(px(2), px(6))); autowrap(lab, 6)

        def update_dup_preview():
            name = self._next_duplicate_name(info)
            dup_preview.set(f"Nombre propuesto: {name}" if name else "No se pudo calcular un nombre consecutivo.")
            return name

        def apply_duplicate():
            name = update_dup_preview()
            if not name:
                messagebox.showwarning(APP_TITLE, "No se pudo generar un nombre consecutivo para este archivo.", parent=win)
                return
            info.expected_name = name
            info.status = "RENOMBRAR"
            info.detail = "Resuelto manualmente como duplicado/consecutivo."
            info.manual_override = True
            self.refresh_tree()
            self.tree.selection_set(str(idx))
            self.tree.see(str(idx))
            self.show_selected_detail()
            win.destroy()

        update_dup_preview()
        ttk.Button(dup_card.body, text="Renombrar como duplicado", command=apply_duplicate).pack(anchor="w")

        # Acción 2: corregir manualmente el tipo de documento.
        type_card = Card(win.outer, L, "Si el detector eligió un tipo incorrecto")
        type_card.pack(fill="x")
        type_frame = ttk.Frame(type_card.body, style="Card.TFrame"); type_frame.pack(fill="x")
        type_frame.columnconfigure(1, weight=1)
        ttk.Label(type_frame, text="Tipo de documento", style="CardBold.TLabel").grid(row=0, column=0, sticky="w")
        current_choice = ""
        dtype = norm(info.declaration_type or "")
        if info.document_kind == "DECLARACION" and dtype == "NORMAL": current_choice = "DECLARACION NORMAL"
        elif info.document_kind == "DECLARACION" and dtype == "COMPLEMENTARIA": current_choice = "DECLARACION COMPLEMENTARIA"
        elif info.document_kind == "ACUSE" and dtype == "NORMAL": current_choice = "ACUSE NORMAL"
        elif info.document_kind == "ACUSE" and dtype == "COMPLEMENTARIA": current_choice = "ACUSE COMPLEMENTARIA"
        type_var = tk.StringVar(value=current_choice or "DECLARACION NORMAL")
        combo = L.combo(type_frame, textvariable=type_var, state="readonly", width=32,
                        values=("DECLARACION NORMAL", "DECLARACION COMPLEMENTARIA", "ACUSE NORMAL", "ACUSE COMPLEMENTARIA"))
        combo.grid(row=0, column=1, sticky="w", padx=(px(8), 0))
        manual_preview = tk.StringVar(value="")
        lab = ttk.Label(type_frame, textvariable=manual_preview, style="Muted.TLabel", justify="left")
        lab.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(px(6), px(6))); autowrap(lab, 6)

        def preview_manual(*_):
            # El método solo modifica kind/type; se guardan y restauran para la vista previa.
            old_kind, old_dtype = info.document_kind, info.declaration_type
            try:
                name = self._manual_name_for_type(info, type_var.get())
            finally:
                info.document_kind, info.declaration_type = old_kind, old_dtype
            if name:
                manual_preview.set(f"Nombre propuesto: {name}")
            elif not info.month:
                manual_preview.set("No se puede calcular el nombre: el mes no está identificado.")
            else:
                manual_preview.set("No se pudo calcular el nombre con los datos disponibles.")
            return name

        def apply_type():
            name = self._manual_name_for_type(info, type_var.get())
            if not name:
                messagebox.showwarning(APP_TITLE, "No se pudo calcular el nombre final. Verifica que el mes esté identificado.", parent=win)
                return
            info.expected_name = name
            info.status = "RENOMBRAR"
            info.detail = f"Tipo de documento seleccionado manualmente: {type_var.get()}."
            info.manual_override = True
            # Si el nombre coincide con otro destino, convertirlo de inmediato
            # en un consecutivo libre para que no vuelva a quedar en conflicto.
            other_names = {
                j.expected_name.casefold()
                for j in self.infos
                if j is not info and j.expected_name and j.status in {"RENOMBRAR", "CORRECTO"}
            }
            if info.expected_name.casefold() in other_names or ((info.path.parent / info.expected_name).exists() and (info.path.parent / info.expected_name).resolve() != info.path.resolve()):
                alt = self._next_duplicate_name(info)
                if alt:
                    info.expected_name = alt
                    info.detail += " Se agregó consecutivo porque el nombre ya estaba ocupado."
            self.refresh_tree()
            self.tree.selection_set(str(idx))
            self.tree.see(str(idx))
            self.show_selected_detail()
            win.destroy()

        combo.bind("<<ComboboxSelected>>", preview_manual)
        preview_manual()
        ttk.Button(type_frame, text="Aplicar tipo seleccionado", command=apply_type).grid(row=2, column=0, columnspan=2, sticky="w")
        win.show()

    def show_detail_popup(self, _event=None):
        selected = self.tree.selection()
        if not selected: return
        info = self.infos[int(selected[0])]
        L = self.look; px = L.px
        win = Dialog(self, L, "Detalle del PDF", size=(680, 620), minsize=(520, 420))
        ttk.Button(win.footer(), text="Cerrar", command=win.close, style="Primary.TButton").pack(side="right")
        area = ScrollArea(win.outer, L, bg="bg", style="Bg.TFrame"); area.pack(fill="both", expand=True)
        card = Card(area.inner, L, info.path.name); card.pack(fill="x")
        grid = ttk.Frame(card.body, style="Card.TFrame"); grid.pack(fill="x", pady=(px(6), 0)); grid.columnconfigure(1, weight=1)
        fields = [("Estado", info.status), ("Detalle", info.detail), ("RFC", info.rfc or "-"), ("Razón social", info.razon_social or "-"),
                  ("Documento", info.document_kind or "-"), ("RESICO", "Sí" if info.is_resico else "No"),
                  ("SALARIOS", "Sí" if info.is_salarios else "No"), ("Consecutivo complementaria", info.complement_sequence or "-"),
                  ("Tipo declaración", info.declaration_type or "-"), ("Tipo complementaria", info.complement_type or "-"),
                  ("Periodo", info.month or "-"), ("Ejercicio", info.year or "-"), ("Número de operación", info.operation or "-"),
                  ("Nombre final", info.expected_name or "-")]
        for r, (key, value) in enumerate(fields):
            ttk.Label(grid, text=key, style="Muted.TLabel").grid(row=r, column=0, sticky="nw", padx=(0, px(16)), pady=px(3))
            lab = ttk.Label(grid, text=str(value), style="Card.TLabel", justify="left")
            lab.grid(row=r, column=1, sticky="ew", pady=px(3)); autowrap(lab, 6)
        win.show()


def main():
    if PdfReader is None:
        root = tk.Tk(); root.withdraw()
        messagebox.showerror(APP_TITLE, "Falta la librería pypdf.\n\nEjecuta CREAR_EXE.bat o instala pypdf con Python.")
        return 1
    app = App(); app.mainloop(); return 0

if __name__ == "__main__":
    raise SystemExit(main())
