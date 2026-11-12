"""Motor extraído de Declara v0.2.6. Regenerar con scripts/extract_declara_engine.py."""


from __future__ import annotations
import hashlib
import os
import re
import tempfile
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional
from pypdf import PdfReader
PYPDF_IMPORT_ERROR = None


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


def next_duplicate_name(info: PdfInfo, infos: list[PdfInfo]) -> Optional[str]:
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
        for j in infos
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


def manual_name_for_type(info: PdfInfo, choice: str, infos: list[PdfInfo], company: str) -> Optional[str]:
    """Construye el nombre estándar al elegir manualmente el tipo."""
    if not info.month:
        return None
    month_number = MONTH_NUMBERS.get(info.month)
    if not month_number:
        return None
    company = sanitize_company_name(company)
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
        for j in infos:
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
