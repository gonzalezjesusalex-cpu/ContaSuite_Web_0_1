"""Vigencia de certificados públicos (.cer) de e.firma y sello digital.

Only the PUBLIC certificate is opened. Private keys (.key), .pfx files and password notes are never read. The dates
are the certificate's own validity window: this is not validation with the SAT, no revocation or chain check.
"""

import math
import re
from datetime import datetime, timezone
from pathlib import PurePosixPath

from .folder_groups import fold

RFC = re.compile(r'(?<![A-Z0-9Ñ&])([A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3})(?![A-Z0-9Ñ&])')
MAX_ROWS = 80
WARN_DAYS = 90  # «Por vencer»: 30 to 90 whole days left (both limits included)
CRITICAL_DAYS = 30  # «Crítico»: fewer than 30 whole days left and still valid
REASONS = {
    'rfc_ajeno': 'El RFC del certificado no es el de esta empresa.',
    'ilegible': 'No se pudo leer como certificado.',
}


def certificate_status(not_after, today, not_before=None):
    """The ONE validity state used everywhere (cambio 2.2): (state, whole days left, floor).

    vigente > 90 days · por_vencer 30..90 inclusive · critico < 30 and still valid · vencido once the date and time
    passed. `aun_no` only when a start date exists and has not arrived yet.
    """
    days = math.floor((not_after - today).total_seconds() / 86400)
    if not_before is not None and today < not_before:
        return 'aun_no', days
    if today > not_after:
        return 'vencido', days
    if days < CRITICAL_DAYS:
        return 'critico', days
    if days <= WARN_DAYS:
        return 'por_vencer', days
    return 'vigente', days


def serial_text(serial):
    """SAT serial number: the certificate's integer is the ASCII of the 20 digits the SAT prints."""
    raw = format(serial, 'x')
    raw = raw.rjust(len(raw) + len(raw) % 2, '0')
    try:
        text = bytes.fromhex(raw).decode('ascii')
        if text.isdigit():
            return text
    except ValueError:
        pass
    return raw.upper()


def certificate_info(data, today, rfc=''):
    """Validity window and RFCs of a public certificate (DER or PEM). ValueError if it cannot be read."""
    from cryptography import x509

    try:
        cert = (
            x509.load_pem_x509_certificate(data)
            if data.lstrip().startswith(b'-----BEGIN')
            else x509.load_der_x509_certificate(data)
        )
    except Exception as exc:  # noqa: BLE001 - any parsing failure means "not a readable certificate"
        raise ValueError('unreadable certificate') from exc
    start, end = cert.not_valid_before_utc, cert.not_valid_after_utc
    state, days = certificate_status(end, today, start)
    rfcs = sorted({r for attr in cert.subject for r in RFC.findall(str(attr.value).upper())})
    issuer = next((str(a.value) for a in cert.issuer if a.oid == x509.NameOID.COMMON_NAME), '')
    return {
        'desde': start.date().isoformat(),
        'hasta': end.date().isoformat(),
        'desde_ts': start.isoformat(),
        'hasta_ts': end.isoformat(),
        'dias': days,
        's': state,
        'rfcs': rfcs,
        'serie': serial_text(cert.serial_number),
        'emisor': issuer[:120],
    }


def holder_kind(path):
    """'FIEL', 'CSD' or 'RL' (legal representative) according to the folders; '' when they do not say."""
    folders = [fold(p) for p in PurePosixPath(path.replace('\\', '/')).parts[:-1]]
    text = ' / '.join(folders)
    if re.search(r'(?<![A-Z0-9])RL(?![A-Z0-9])', text):
        return 'RL'
    if re.search(r'SELLO|\bCSD\b', text):
        return 'CSD'
    if re.search(r'FIEL|E-?FIRMA', text):
        return 'FIEL'
    return ''


class CertIndex:
    def __init__(self, rfc=''):
        self.rfc = ''.join((rfc or '').split()).upper()
        self.items = []
        self.serials = {}

    def add(self, path, data, today=None):
        today = today or datetime.now(timezone.utc)
        row = {'p': path, 'k': holder_kind(path)}
        try:
            info = certificate_info(data, today, self.rfc)
        except (ValueError, ImportError):
            self.items.append(
                {
                    **row,
                    'desde': '',
                    'hasta': '',
                    'dias': None,
                    's': 'ilegible',
                    'rfcs': [],
                    'emp': False,
                    'why': 'ilegible',
                }
            )
            return
        # The same certificate copied into several folders counts once (by serial number).
        seen = self.serials.get(info['serie'])
        if seen is not None:
            if not seen['k'] and row['k']:
                seen['k'] = row['k']
            return
        mine = bool(self.rfc and self.rfc in info['rfcs'])
        # Only a sello digital must carry the company's RFC; a FIEL may belong to its legal representative.
        why = 'rfc_ajeno' if self.rfc and info['rfcs'] and not mine and row['k'] in {'CSD', ''} else ''
        item = {**row, **info, 'emp': mine, 'why': why}
        self.serials[info['serie']] = item
        self.items.append(item)

    def result(self):
        urgent = {'vencido', 'critico', 'por_vencer', 'ilegible'}
        rows = sorted(self.items, key=lambda r: (r['s'] not in urgent, r['hasta']))[:MAX_ROWS]
        count = lambda state: sum(1 for r in self.items if r['s'] == state)  # noqa: E731
        return {
            'rows': rows,
            'total': len(self.items),
            'vigentes': count('vigente'),
            'por_vencer': count('por_vencer'),
            'criticos': count('critico'),
            'vencidos': count('vencido'),
            'revisar': sum(1 for r in self.items if r['why']),
        }
