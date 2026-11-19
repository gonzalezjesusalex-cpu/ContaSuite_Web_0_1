"""Content review of an Organizador CFDI plan (cambios 5.1 to 5.4). Read only; the engine is not changed.

The engine classifies by PATH only and never fills `Item.uuid`. This module looks at the content of the files the plan
selected (UUID, date, RFCs, type; never amounts) and says whether it agrees with the folder, and how each file stands
against the company's expediente. The adapter never registers an RFC or period that contradicts the XML in silence.
"""

import hashlib
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from . import recopila_enrich as shared

RFC_FOLDER = re.compile(r'^[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}$')
PDF_PAGES = 5
INCOHERENCE = {
    'xml_ilegible': 'El XML no se pudo leer como CFDI.',
    'emisor_distinto': 'El emisor no es la empresa y el archivo está en Emitidos.',
    'receptor_distinto': 'El receptor no es la empresa y el archivo está en Recibidos.',
    'periodo_distinto': 'La fecha del CFDI está fuera del mes de la carpeta.',
    'pareja_bloqueada': 'Su pareja XML tiene una incoherencia.',
}
OMITTED = {
    'otro_rfc': 'Carpeta de otro RFC',
    'mes_no_elegido': 'Mes no elegido',
    'subcarpeta': 'Está en una subcarpeta (no se recorre)',
    'extension': 'Extensión no elegida',
    'fuera_de_ruta': 'No está en una ruta Tipo/RFC/AAAA-MM',
}


def sha256_of(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def xml_header(path):
    """UUID, date, RFCs and type of a CFDI XML, or None when it cannot be read as a CFDI."""
    details = shared.cfdi_details(path)
    if not details:
        return None
    uuid = ''
    try:
        for node in ET.parse(path).getroot().iter():
            if shared.motor.local_name(node.tag) == 'TimbreFiscalDigital':
                uuid = shared.motor.norm_uuid(node.attrib.get('UUID', '') or node.attrib.get('Uuid', ''))
    except ET.ParseError:
        uuid = ''
    return {
        'uuid': uuid,
        'fecha': details['fecha'],
        'emisor': details['emisor'],
        'receptor': details['receptor'],
        'tipo': details['tipo'],
    }


def review(plan):
    """Per planned file: content facts, incoherences, XML-PDF pair (only by the UUID in the PDF text)."""
    rfc = plan.options.rfc
    source = Path(plan.options.source)
    rows = {}
    for item in plan.ready:
        path = Path(item.source)
        ext = path.suffix.lower()
        if ext not in ('.xml', '.pdf'):
            continue
        rel = path.relative_to(source).as_posix()
        row = {
            'path': rel,
            'name': path.name,
            'ext': ext,
            'kind': item.kind,
            'period': item.date,
            'uuid': '',
            'fecha': '',
            'emisor': '',
            'receptor': '',
            'tipo': '',
            'incoherence': [],
            'pair': 'sin_pareja_identificada',
            'partner': '',
            'warnings': [],
        }
        if ext == '.xml':
            header = xml_header(path)
            if header is None or not header['uuid']:
                row['incoherence'].append('xml_ilegible')
            else:
                row.update(header)
                if item.kind == 'Emitidos' and header['emisor'] != rfc:
                    row['incoherence'].append('emisor_distinto')
                if item.kind == 'Recibidos' and header['receptor'] != rfc:
                    row['incoherence'].append('receptor_distinto')
                if header['fecha'][:7] != item.date:
                    row['incoherence'].append('periodo_distinto')
        else:
            found, _text = shared.pdf_uuids(path, PDF_PAGES)
            row['pdf_uuids'] = sorted(found)
        rows[rel] = row
    xml_by_uuid = {r['uuid']: r for r in rows.values() if r['ext'] == '.xml' and r['uuid']}
    paired = set()
    for row in rows.values():
        if row['ext'] != '.pdf':
            continue
        # The pair is identified only by the UUID in the PDF text: never by the file name.
        for uuid in row.pop('pdf_uuids', []):
            if uuid in xml_by_uuid:
                xml_row = xml_by_uuid[uuid]
                row.update(uuid=uuid, pair='identificada', partner=xml_row['path'])
                xml_row.update(pair='identificada', partner=row['path'])
                paired.add(xml_row['path'])
                if xml_row['incoherence']:
                    row['incoherence'].append('pareja_bloqueada')
                break
    for row in rows.values():
        row.pop('pdf_uuids', None)
        if row['ext'] == '.xml' and row['pair'] != 'identificada' and 'xml_ilegible' not in row['incoherence']:
            row['warnings'].append('xml_sin_pdf')
        if row['ext'] == '.pdf' and row['pair'] != 'identificada':
            row['warnings'].append('pdf_sin_xml')
    return rows


def omitted_files(plan):
    """Every file under the input that the plan did not select, with the reason (cambio 5.3)."""
    o = plan.options
    root = Path(o.source)
    selected = {Path(i.source).resolve() for i in plan.items if i.state == 'Listo'}
    wanted = {f'{o.year}-{m:02d}' for m in o.months}
    out = []
    for path in sorted(root.rglob('*')):
        if not path.is_file() or path.resolve() in selected:
            continue
        parts = path.relative_to(root).parts
        reason = 'fuera_de_ruta'
        if len(parts) >= 4 and parts[0].casefold() in ('emitidos', 'recibidos'):
            _kind, folder_rfc, period = parts[0], parts[1], parts[2]
            if folder_rfc.upper() != o.rfc:
                reason = 'otro_rfc'
            elif period not in wanted:
                reason = 'mes_no_elegido'
            elif len(parts) > 4:
                reason = 'subcarpeta'
            elif path.suffix.lower() not in o.extensions:
                reason = 'extension'
            elif parts[0].casefold() not in {k.casefold() for k in o.kinds}:
                reason = 'fuera_de_ruta'
        elif parts[0].casefold() == 'reportes':
            reason = 'fuera_de_ruta'
        out.append({'path': '/'.join(parts), 'reason': reason})
    return out


def foreign_rfc_folders(source, rfc):
    """RFC-shaped folders under Emitidos/Recibidos that are not the company's (cambio 5.1 warning)."""
    root = Path(source)
    found = set()
    for kind in root.iterdir() if root.is_dir() else []:
        if kind.is_dir() and kind.name.casefold() in ('emitidos', 'recibidos'):
            for child in kind.iterdir():
                if child.is_dir() and RFC_FOLDER.fullmatch(child.name.upper()) and child.name.upper() != rfc:
                    found.add(child.name.upper())
    return sorted(found)


def against_expediente(db, company_id, rows, source):
    """Stand of each XML/PDF against the company's expediente (cambio 5.4).

    ya_registrado: same SHA-256 AND already linked to this company. revision: same SHA linked to another company or
    to none, or the same UUID with different content. nuevo: everything else. Never merges or overwrites.
    """
    from sqlalchemy import select

    from . import document_identity as identity
    from .models import Document, DocumentCompanyLink, DocumentVersion

    result = {}
    linked = {
        x
        for (x,) in db.execute(
            select(DocumentCompanyLink.document_id).where(DocumentCompanyLink.company_id == company_id)
        )
    }
    for rel, row in rows.items():
        digest = sha256_of(Path(source) / rel)
        entry = {'sha256': digest, 'state': 'nuevo', 'reason': ''}
        same = db.execute(
            select(Document.id, Document.company_id)
            .join(DocumentVersion, DocumentVersion.document_id == Document.id)
            .where(DocumentVersion.sha256 == digest)
        ).all()
        if any(d.company_id == company_id or d.id in linked for d in same):
            entry['state'] = 'ya_registrado'
        elif same:
            entry.update(state='revision', reason='mismo_sha_otra_empresa')
        elif row['uuid'] and identity.available(db):
            clash = db.scalar(
                select(identity.identities.c.version_id)
                .where(identity.identities.c.uuid == row['uuid'], identity.identities.c.content_hash != digest)
                .limit(1)
            )
            if clash:
                entry.update(state='revision', reason='uuid_contenido_distinto')
        result[rel] = entry
    return result
