"""Enrichment of a Recopila analysis (cambio 4.1). Runs after `motor.analyze()` and before `motor.generate_all()`.

The original engine (`recopila_engine.py`) is NOT changed: this module only reads its `AnalysisResult` and the XML/PDF of
the same input. It never reads or compares amounts. Everything it adds is a PROPOSAL or a review mark; nothing becomes a
relation of the generated files until a person accepts it (cambio 4.2).
"""

import re
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path

from . import recopila_engine as motor

COMPLETE, PARTIAL, XML_ONLY, NO_SUPPORT = 'Completa', 'Parcial', 'XML sin PDF', 'Sin soporte'
CATEGORIES = ('ingresos', 'egresos', 'nomina', 'complementos', 'otro_periodo', 'otro')
PDF_TEXT_PAGES = 5
FOREIGN_SCAN_PAGES = 1500  # budget of pages read looking for policies in a format the engine does not know
FOREIGN_HINT = re.compile(r'contalink', re.I)
FOREIGN_POLICY = re.compile(r'p[oó]liza', re.I)
FOREIGN_TABLE = re.compile(r'\b(debe|haber)\b', re.I)


def cfdi_details(path):
    """Public header data of a CFDI XML; amounts are deliberately not read."""
    try:
        root = ET.parse(path).getroot()
    except Exception:  # noqa: BLE001 - an unreadable XML has no details
        return {}
    out = {
        'tipo': root.attrib.get('TipoDeComprobante', ''),
        'serie': root.attrib.get('Serie', ''),
        'folio': root.attrib.get('Folio', ''),
        'metodo_pago': root.attrib.get('MetodoPago', ''),
        'fecha': root.attrib.get('Fecha', ''),
        'emisor': '',
        'receptor': '',
        'uso': '',
        'cancelacion': None,  # an XML never says it: unknown unless an external status is available
    }
    for node in root.iter():
        name = motor.local_name(node.tag)
        if name == 'Emisor':
            out['emisor'] = node.attrib.get('Rfc', '').upper()
        elif name == 'Receptor':
            out['receptor'] = node.attrib.get('Rfc', '').upper()
            out['uso'] = node.attrib.get('UsoCFDI', '')
    return out


def pdf_uuids(path, pages=PDF_TEXT_PAGES):
    """(UUIDs found in the text of the first pages, whether any text was found)."""
    try:
        reader = motor.PdfReader(str(path))
        text = ''
        for page in reader.pages[:pages]:
            text += (page.extract_text() or '') + '\n'
    except Exception:  # noqa: BLE001 - unreadable PDF: no text
        return set(), False
    return set(motor.find_uuids(text)), bool(text.strip())


def _rel(root, path):
    try:
        return str(Path(path).relative_to(root)).replace('\\', '/')
    except ValueError:
        return Path(path).name


def _category(record, info, rfc, months):
    if record.is_payment_complement:
        return 'complementos'
    if info.get('tipo') == 'N':
        return 'nomina'
    period = (info.get('fecha') or '')[:7]
    if months and period and period not in months:
        return 'otro_periodo'
    if rfc and info.get('emisor') == rfc and info.get('tipo') in ('I', 'E', ''):
        return 'ingresos'
    if rfc and info.get('receptor') == rfc:
        return 'egresos'
    return 'otro'


def foreign_policy_pages(result, cfdi_pdfs):
    """Pages of PDFs that look like accounting policies in a format the engine cannot read (cambio 4.7).

    Detection only: nothing is parsed. Contalink is recognised by its name when it appears; the reader waits for a
    sample, so the format is never guessed.
    """
    parsed = {p.source_pdf for p in result.policies}
    root = Path(result.root)
    pages = 0
    hinted = False
    budget = FOREIGN_SCAN_PAGES
    # One pass over every file: on case-insensitive file systems two globs (.pdf and .PDF) list the same file twice.
    for pdf in sorted(f for f in root.rglob('*') if f.suffix.lower() == '.pdf'):
        key = str(pdf)
        if key in parsed or key in cfdi_pdfs or budget <= 0:
            continue
        try:
            reader = motor.PdfReader(key)
            for page in reader.pages[:budget]:
                budget -= 1
                text = page.extract_text() or ''
                if FOREIGN_HINT.search(text):
                    hinted = True
                if FOREIGN_POLICY.search(text) and FOREIGN_TABLE.search(text):
                    pages += 1
        except Exception:  # noqa: BLE001 - unreadable PDFs are reported elsewhere
            continue
    return {'pages': pages, 'contalink_hint': hinted}


def build(result, company_rfc=''):
    rfc = ''.join((company_rfc or '').split()).upper()
    root = Path(result.root)
    details, by_uuid, complements = {}, defaultdict(list), defaultdict(list)
    for record in result.cfdis:
        by_uuid[record.uuid].append(record)
        if record.is_payment_complement:
            for related in record.related_uuids:
                complements[related].append(record)
        if record.uuid not in details:
            details[record.uuid] = cfdi_details(record.xml_path)
    # XML-PDF pair: the engine pairs by file name; the pair is verified only if the PDF text carries the UUID.
    pair = {}
    for record in result.cfdis:
        if not record.pdf_path:
            pair[record.uuid] = 'sin_pdf'
            continue
        found, has_text = pdf_uuids(record.pdf_path)
        pair[record.uuid] = 'verificada' if record.uuid in found else 'sin_texto' if not has_text else 'no_verificada'
    months = set(result.summary.get('months', {}))
    policies, proposals, review = [], [], []

    def direct(uuid):
        return [r for r in by_uuid.get(uuid, []) if not r.is_payment_complement]

    for index, pol in enumerate(result.policies):
        supported, xml_only, missing = [], [], []
        for uuid in pol.uuids:
            if pol.policy_type in motor.PAYMENT_TYPES:
                pool = complements.get(uuid, [])
            elif pol.policy_type in motor.DIRECT_TYPES:
                pool = direct(uuid)
            else:
                pool = []
            if any(r.pdf_path for r in pool) and any(p in pol.matched_pdfs for p in (r.pdf_path for r in pool)):
                supported.append(uuid)
            elif pool or by_uuid.get(uuid):
                xml_only.append(uuid)
            else:
                missing.append(uuid)
        if pol.uuids and len(supported) == len(pol.uuids):
            status = COMPLETE
        elif supported:
            status = PARTIAL
        elif xml_only and not any(r.pdf_path for u in xml_only for r in by_uuid.get(u, [])):
            status = XML_ONLY
        else:
            status = NO_SUPPORT
        policies.append(
            {
                'index': index,
                'status': status,
                'supported': supported,
                'missing': xml_only + missing,
            }
        )
        # Proposals the engine does not make: the complement itself in a Pago/Cobro, or a CFDI in a Diario.
        for uuid in pol.uuids:
            extra = []
            if pol.policy_type in motor.PAYMENT_TYPES:
                extra = [(r, 'complemento_directo') for r in by_uuid.get(uuid, []) if r.is_payment_complement]
            elif pol.policy_type == 'Diario (Manual)':
                extra = [(r, 'diario') for r in direct(uuid)]
            for record, kind in extra:
                if record.pdf_path and record.pdf_path not in pol.matched_pdfs:
                    key = f'{index}:{kind}:{record.uuid}'
                    if not any(p['id'] == key for p in proposals):
                        proposals.append(
                            {
                                'id': key,
                                'policy_index': index,
                                'kind': kind,
                                'uuid': record.uuid,
                                'pdf': _rel(root, record.pdf_path),
                            }
                        )
        if rfc:
            for uuid in pol.uuids if pol.matched_pdfs else []:
                info = details.get(uuid) or {}
                if not info:
                    continue
                if pol.policy_type == 'Venta (Ingreso)' and info.get('emisor') and info['emisor'] != rfc:
                    review.append({'kind': 'rfc_ajeno', 'uuid': uuid, 'policy_index': index})
                elif pol.policy_type == 'Compra (Egreso)' and info.get('receptor') and info['receptor'] != rfc:
                    review.append({'kind': 'rfc_ajeno', 'uuid': uuid, 'policy_index': index})
    flagged = {r['uuid'] for r in review}
    for record in result.cfdis:
        info = details.get(record.uuid) or {}
        if rfc and info and rfc not in (info.get('emisor'), info.get('receptor')) and record.uuid not in flagged:
            review.append({'kind': 'rfc_ajeno', 'uuid': record.uuid, 'policy_index': None})
            flagged.add(record.uuid)
        if record.pdf_path and pair.get(record.uuid) in ('no_verificada', 'sin_texto'):
            review.append({'kind': 'pareja_no_verificada', 'uuid': record.uuid, 'policy_index': None})
    by_pdf = {r.pdf_path: r for r in result.cfdis if r.pdf_path}
    leftovers = []
    for pdf in result.leftovers:
        record = by_pdf.get(pdf)
        info = details.get(record.uuid, {}) if record else {}
        leftovers.append(
            {
                'pdf': _rel(root, pdf),
                'uuid': record.uuid if record else '',
                'category': _category(record, info, rfc, months) if record else 'otro',
            }
        )
    month_detail = {}
    for pol, entry in zip(result.policies, policies, strict=True):
        if not pol.month:
            continue
        row = month_detail.setdefault(
            pol.month,
            {'policies': 0, COMPLETE: 0, PARTIAL: 0, XML_ONLY: 0, NO_SUPPORT: 0, 'facturas_sin_poliza': 0},
        )
        row['policies'] += 1
        row[entry['status']] += 1
    for pdf in result.leftovers:
        record = by_pdf.get(pdf)
        period = ((details.get(record.uuid, {}) if record else {}).get('fecha') or '')[:7]
        if period in month_detail:
            month_detail[period]['facturas_sin_poliza'] += 1
    # Public CFDI data by UUID (no file paths, no amounts).
    public = {uuid: {**info, 'pareja': pair.get(uuid, 'sin_pdf')} for uuid, info in details.items()}
    return {
        'policies': policies,
        'proposals': proposals,
        'review': review,
        'leftovers': leftovers,
        'leftover_categories': dict(Counter(item['category'] for item in leftovers)),
        'cfdis': public,
        'months': month_detail,
        'unsupported': foreign_policy_pages(result, {r.pdf_path for r in result.cfdis if r.pdf_path}),
    }


def apply_adjustments(result, adjustments):
    """Apply confirmed adjustments to an `AnalysisResult` (never to the engine). `adjustments` are dicts with
    `policy_idx`, `action` ('attach' | 'remove') and `target` (PDF path relative to the analysis root)."""
    root = Path(result.root)
    leftovers = list(result.leftovers)
    for adj in adjustments:
        if adj.get('revoked_at') or not 0 <= adj['policy_idx'] < len(result.policies):
            continue
        pol = result.policies[adj['policy_idx']]
        absolute = str((root / adj['target']).resolve())
        known = {Path(p).resolve(): p for p in [*pol.matched_pdfs, *leftovers]}
        target = known.get(Path(absolute).resolve(), absolute if Path(absolute).is_file() else None)
        if not target:
            continue
        if adj['action'] == 'attach' and target not in pol.matched_pdfs:
            pol.matched_pdfs.append(target)
            leftovers = [x for x in leftovers if x != target]
        elif adj['action'] == 'remove' and target in pol.matched_pdfs:
            pol.matched_pdfs.remove(target)
            if not any(target in other.matched_pdfs for other in result.policies):
                leftovers.append(target)
        pol.match_status = (
            'RELACIONADO'
            if pol.matched_pdfs
            else ('POLIZA_SOLA_DIARIO' if pol.policy_type == 'Diario (Manual)' else 'POLIZA_SOLA_SIN_DOCUMENTO')
        )
    result.leftovers = sorted(set(leftovers))
    return result
