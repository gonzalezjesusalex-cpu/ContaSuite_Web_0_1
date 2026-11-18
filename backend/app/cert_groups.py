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
SOON_DAYS = 30
REASONS = {
    'rfc_ajeno': 'El RFC del certificado no es el de esta empresa.',
    'ilegible': 'No se pudo leer como certificado.',
}


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
    days = math.ceil((end - today).total_seconds() / 86400)
    state = (
        'aun_no' if today < start else 'vencido' if today > end else 'por_vencer' if days <= SOON_DAYS else 'vigente'
    )
    rfcs = sorted({r for attr in cert.subject for r in RFC.findall(str(attr.value).upper())})
    return {'desde': start.date().isoformat(), 'hasta': end.date().isoformat(), 'dias': days, 's': state, 'rfcs': rfcs}


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
        mine = bool(self.rfc and self.rfc in info['rfcs'])
        # Only a sello digital must carry the company's RFC; a FIEL may belong to its legal representative.
        why = 'rfc_ajeno' if self.rfc and info['rfcs'] and not mine and row['k'] in {'CSD', ''} else ''
        self.items.append({**row, **info, 'emp': mine, 'why': why})

    def result(self):
        rows = sorted(self.items, key=lambda r: (r['s'] not in {'vencido', 'por_vencer', 'ilegible'}, r['hasta']))[
            :MAX_ROWS
        ]
        count = lambda state: sum(1 for r in self.items if r['s'] == state)  # noqa: E731
        return {
            'rows': rows,
            'total': len(self.items),
            'vigentes': count('vigente'),
            'por_vencer': count('por_vencer'),
            'vencidos': count('vencido'),
            'revisar': sum(1 for r in self.items if r['why']),
        }
