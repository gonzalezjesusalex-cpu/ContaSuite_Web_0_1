from __future__ import annotations

import csv
import json
import re
import shutil
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable
import xml.etree.ElementTree as ET

from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter

UUID_RE = re.compile(r"(?i)(?<![0-9a-f])([0-9a-f]{8})\s*-\s*([0-9a-f]{4})\s*-\s*([0-9a-f]{4})\s*-\s*([0-9a-f]{4})\s*-\s*([0-9a-f]{12})")
DATE_RE = re.compile(r"\b(\d{2}/\d{2}/\d{4})\b")
DIRECT_TYPES = {"Venta (Ingreso)", "Compra (Egreso)", "Nómina (Egreso)"}
PAYMENT_TYPES = {"Cobro (Ingreso)", "Pago (Egreso)"}
MONTH_NAMES = {1:"ENERO",2:"FEBRERO",3:"MARZO",4:"ABRIL",5:"MAYO",6:"JUNIO",7:"JULIO",8:"AGOSTO",9:"SEPTIEMBRE",10:"OCTUBRE",11:"NOVIEMBRE",12:"DICIEMBRE"}


def norm_uuid(value: str) -> str:
    m = UUID_RE.search(value or "")
    return "-".join(x.upper() for x in m.groups()) if m else ""


def find_uuids(text: str) -> list[str]:
    out, seen = [], set()
    for m in UUID_RE.finditer(text or ""):
        u = "-".join(x.upper() for x in m.groups())
        if u not in seen:
            seen.add(u); out.append(u)
    return out


def local_name(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag.split(":")[-1]


@dataclass
class CfdiRecord:
    uuid: str
    xml_path: str
    pdf_path: str | None
    cfdi_type: str | None
    issue_date: str | None
    is_payment_complement: bool
    related_uuids: list[str]


@dataclass
class PolicyRecord:
    source_pdf: str
    page: int
    policy_type: str
    date: str
    month: str
    description: str
    uuids: list[str]
    matched_pdfs: list[str] = field(default_factory=list)
    match_status: str = "PENDIENTE"

    @property
    def section(self) -> str:
        if self.policy_type in {"Compra (Egreso)", "Pago (Egreso)", "Nómina (Egreso)"}:
            return "EGRESOS"
        if self.policy_type in {"Venta (Ingreso)", "Cobro (Ingreso)"}:
            return "INGRESOS"
        return "DIARIO"


@dataclass
class AnalysisResult:
    root: str
    policies: list[PolicyRecord]
    cfdis: list[CfdiRecord]
    leftovers: list[str]
    summary: dict


def parse_cfdi_xml(path: Path, pdf_by_stem: dict[str, Path]) -> CfdiRecord | None:
    try:
        root = ET.parse(path).getroot()
    except Exception:
        return None
    uuid, related, is_payment = "", [], False
    for elem in root.iter():
        ln = local_name(elem.tag).lower()
        if ln == "timbrefiscaldigital":
            uuid = norm_uuid(elem.attrib.get("UUID", "") or elem.attrib.get("Uuid", "")) or uuid
        elif ln == "doctorelacionado":
            candidate = norm_uuid(elem.attrib.get("IdDocumento", "") or elem.attrib.get("IDDocumento", ""))
            if candidate: related.append(candidate)
        elif ln in {"pagos", "pago"} and "pago" in elem.tag.lower():
            is_payment = True
    if related: is_payment = True
    attrs = root.attrib
    if not uuid: uuid = norm_uuid(path.stem)
    if not uuid: return None
    pdf = pdf_by_stem.get(path.stem.upper()) or pdf_by_stem.get(uuid.upper())
    return CfdiRecord(uuid, str(path), str(pdf) if pdf else None,
                      attrs.get("TipoDeComprobante") or attrs.get("tipodecomprobante"),
                      attrs.get("Fecha") or attrs.get("fecha"), is_payment, sorted(set(related)))


def normalize_policy_type(text: str) -> str | None:
    compact = re.sub(r"\s+", " ", text)
    patterns = [
        (r"Venta\s*\(\s*Ingreso\s*\)", "Venta (Ingreso)"),
        (r"Cobro\s*\(\s*Ingreso\s*\)", "Cobro (Ingreso)"),
        (r"Compra\s*\(\s*Egreso\s*\)", "Compra (Egreso)"),
        (r"Pago\s*\(\s*Egreso\s*\)", "Pago (Egreso)"),
        (r"N[oó]mina\s*\(\s*Egreso\s*\)", "Nómina (Egreso)"),
        (r"Diario\s*\(\s*Manual\s*\)", "Diario (Manual)"),
    ]
    for pat, label in patterns:
        if re.search(pat, compact, re.I): return label
    return None


def extract_description(text: str) -> str:
    m = re.search(r"Descripci[oó]n\s+([^\n]+)", text, re.I)
    return m.group(1).strip()[:160] if m else ""


def parse_policy_pdf(path: Path) -> list[PolicyRecord]:
    try: reader = PdfReader(str(path))
    except Exception: return []
    records = []
    for idx, page in enumerate(reader.pages, 1):
        try: text = page.extract_text() or ""
        except Exception: continue
        upper = text.upper()
        if "IMPRESO DE PÓLIZAS" not in upper and "IMPRESO DE POLIZAS" not in upper: continue
        ptype = normalize_policy_type(text)
        if not ptype: continue
        dm = re.search(r"Fecha\s+(\d{2}/\d{2}/\d{4})", text, re.I)
        dates = DATE_RE.findall(text)
        date = dm.group(1) if dm else (dates[-1] if dates else "")
        month = ""
        if date:
            dd, mm, yyyy = date.split("/"); month = f"{yyyy}-{mm}"
        low = text.lower(); pos = low.find("cfdi asociados a la póliza")
        if pos < 0: pos = low.find("cfdi asociados a la poliza")
        uuids = find_uuids(text[pos:] if pos >= 0 else text)
        records.append(PolicyRecord(str(path), idx, ptype, date, month, extract_description(text), uuids))
    return records


def _materialize_input(input_path: Path, work_dir: Path) -> Path:
    source = work_dir / "entrada"
    if source.exists(): shutil.rmtree(source)
    source.mkdir(parents=True)
    if input_path.is_dir():
        # Use original folder directly; PDFs remain untouched.
        return input_path.resolve()
    if input_path.suffix.lower() != ".zip": raise ValueError("Selecciona una carpeta o un archivo .zip")
    with zipfile.ZipFile(input_path, "r") as zf: zf.extractall(source)
    return source


def analyze(input_path: Path, work_dir: Path, progress: Callable[[str], None] | None = None) -> AnalysisResult:
    progress = progress or (lambda _: None)
    root = _materialize_input(input_path.resolve(), work_dir.resolve())
    progress("Buscando PDF y XML…")
    pdfs = list(dict.fromkeys(list(root.rglob("*.pdf")) + list(root.rglob("*.PDF"))))
    xmls = list(dict.fromkeys(list(root.rglob("*.xml")) + list(root.rglob("*.XML"))))
    pdf_by_stem = {p.stem.upper(): p for p in pdfs}

    progress("Leyendo CFDI/XML…")
    cfdis = [r for x in xmls if (r := parse_cfdi_xml(x, pdf_by_stem))]
    cfdi_by_uuid, complement_by_related = defaultdict(list), defaultdict(list)
    for c in cfdis:
        cfdi_by_uuid[c.uuid].append(c)
        if c.is_payment_complement:
            for u in c.related_uuids: complement_by_related[u].append(c)

    progress("Leyendo pólizas…")
    policies, policy_files = [], set()
    for p in pdfs:
        recs = parse_policy_pdf(p)
        if recs: policies.extend(recs); policy_files.add(str(p))

    progress("Relacionando UUID…")
    used = set()
    for pol in policies:
        matches = []
        if pol.policy_type in DIRECT_TYPES:
            for u in pol.uuids:
                for c in cfdi_by_uuid.get(u, []):
                    if not c.is_payment_complement and c.pdf_path: matches.append(c.pdf_path)
        elif pol.policy_type in PAYMENT_TYPES:
            for u in pol.uuids:
                for c in complement_by_related.get(u, []):
                    if c.pdf_path: matches.append(c.pdf_path)
        matches = list(dict.fromkeys(matches)); pol.matched_pdfs = matches; used.update(matches)
        if pol.policy_type == "Diario (Manual)": pol.match_status = "POLIZA_SOLA_DIARIO"
        elif matches: pol.match_status = "RELACIONADO"
        else: pol.match_status = "POLIZA_SOLA_SIN_DOCUMENTO"

    all_cfdi_pdfs = {c.pdf_path for c in cfdis if c.pdf_path}
    leftovers = sorted(x for x in all_cfdi_pdfs if x not in used)
    policy_counts, status_counts = Counter(p.policy_type for p in policies), Counter(p.match_status for p in policies)
    month_counts = Counter(p.month for p in policies if p.month)
    months_desc = sorted(month_counts.keys(), reverse=True)
    summary = {
        "pdf_total": len(pdfs), "xml_total": len(xmls), "cfdi_xml_parsed": len(cfdis),
        "policy_pdf_files": len(policy_files), "policy_pages": len(policies),
        "policy_types": dict(sorted(policy_counts.items())), "policy_status": dict(sorted(status_counts.items())),
        "months": dict(sorted(month_counts.items())), "months_desc": months_desc,
        "policies_with_document": sum(bool(p.matched_pdfs) for p in policies),
        "policies_without_document": sum(not p.matched_pdfs for p in policies),
        "unique_cfdi_pdfs_used": len(used), "leftover_cfdi_pdfs": len(leftovers),
    }
    progress("Análisis terminado")
    return AnalysisResult(str(root), policies, cfdis, leftovers, summary)


def _date_key(date: str):
    try: return datetime.strptime(date, "%d/%m/%Y")
    except Exception: return datetime.min


def sorted_policies(result: AnalysisResult) -> list[PolicyRecord]:
    sec_order = {"EGRESOS": 0, "INGRESOS": 1, "DIARIO": 2}
    def key(p: PolicyRecord):
        try:
            year, month = (int(x) for x in p.month.split("-"))
        except Exception:
            year, month = 0, 0
        # Mes más reciente primero; dentro del mes: Egresos, Ingresos, Diario;
        # dentro de cada sección, fecha cronológica ascendente.
        return (-year, -month, sec_order[p.section], _date_key(p.date), p.source_pdf, p.page)
    return sorted(result.policies, key=key)


def save_reports(result: AnalysisResult, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    with open(output_dir / "resumen.json", "w", encoding="utf-8") as f:
        json.dump(result.summary, f, ensure_ascii=False, indent=2)
    with open(output_dir / "reporte_polizas.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f); w.writerow(["mes","fecha","seccion","tipo_poliza","descripcion","uuid_poliza","estado","documentos_relacionados","pdf_poliza","pagina"])
        for p in sorted_policies(result):
            w.writerow([p.month,p.date,p.section,p.policy_type,p.description," | ".join(p.uuids),p.match_status," | ".join(p.matched_pdfs),p.source_pdf,p.page])
    with open(output_dir / "sobrantes.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f); w.writerow(["pdf_sobrante"]); [w.writerow([x]) for x in result.leftovers]


def generate_recopilador(result: AnalysisResult, dest: Path, progress: Callable[[str], None] | None = None):
    progress = progress or (lambda _: None)
    writer = PdfWriter(); ordered = sorted_policies(result)
    for i, pol in enumerate(ordered, 1):
        progress(f"Recopilador: póliza {i}/{len(ordered)}")
        r = PdfReader(pol.source_pdf); writer.add_page(r.pages[pol.page-1])
        for doc in pol.matched_pdfs:
            try:
                rr = PdfReader(doc)
                for page in rr.pages: writer.add_page(page)
            except Exception: pass
    with open(dest, "wb") as f: writer.write(f)


def generate_sobrantes(result: AnalysisResult, dest: Path, progress: Callable[[str], None] | None = None):
    progress = progress or (lambda _: None)
    writer = PdfWriter()
    for i, doc in enumerate(result.leftovers, 1):
        progress(f"Sobrantes: {i}/{len(result.leftovers)}")
        try:
            rr = PdfReader(doc)
            for page in rr.pages: writer.add_page(page)
        except Exception: pass
    with open(dest, "wb") as f: writer.write(f)


def generate_separadores(result: AnalysisResult, dest: Path):
    months = result.summary.get("months_desc", [])
    c = canvas.Canvas(str(dest), pagesize=letter)
    width, height = letter
    for ym in months:
        try: month_num = int(ym.split("-")[1]); name = MONTH_NAMES[month_num]
        except Exception: name = ym
        # Maximize font size while leaving a modest margin.
        size = 150
        while size > 20 and c.stringWidth(name, "Helvetica-Bold", size) > width - 48:
            size -= 2
        c.setFont("Helvetica-Bold", size)
        # reportlab's baseline needs a slight optical correction for vertical centering.
        c.drawCentredString(width/2, height/2 - size*0.32, name)
        c.showPage()
    c.save()


def generate_recopiladores_por_mes(result: AnalysisResult, output_dir: Path, progress: Callable[[str], None] | None = None):
    """Genera un recopilador independiente por cada mes detectado."""
    progress = progress or (lambda _: None)
    monthly_dir = output_dir / "POR_MESES"
    monthly_dir.mkdir(parents=True, exist_ok=True)

    ordered = sorted_policies(result)
    for ym in result.summary.get("months_desc", []):
        month_policies = [p for p in ordered if p.month == ym]
        if not month_policies:
            continue
        try:
            year, month = ym.split("-")
            month_name = MONTH_NAMES.get(int(month), month).upper()
            filename = f"{year}-{month}_{month_name}.pdf"
        except Exception:
            month_name = ym
            filename = f"{ym}.pdf"

        progress(f"Generando {month_name}: {len(month_policies)} pólizas…")
        writer = PdfWriter()
        for pol in month_policies:
            try:
                r = PdfReader(pol.source_pdf)
                writer.add_page(r.pages[pol.page-1])
            except Exception:
                continue
            for doc in pol.matched_pdfs:
                try:
                    rr = PdfReader(doc)
                    for page in rr.pages:
                        writer.add_page(page)
                except Exception:
                    pass
        with open(monthly_dir / filename, "wb") as f:
            writer.write(f)
    return monthly_dir


def generate_all(result: AnalysisResult, output_dir: Path, progress: Callable[[str], None] | None = None, generate_by_month: bool = False):
    output_dir.mkdir(parents=True, exist_ok=True)
    save_reports(result, output_dir)
    generate_recopilador(result, output_dir / "RECOPILADOR.pdf", progress)
    generate_sobrantes(result, output_dir / "SOBRANTES.pdf", progress)
    generate_separadores(result, output_dir / "SEPARADORES_MESES.pdf")
    if generate_by_month:
        generate_recopiladores_por_mes(result, output_dir, progress)
    return output_dir
