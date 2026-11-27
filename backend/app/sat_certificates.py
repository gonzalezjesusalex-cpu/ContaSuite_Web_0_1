"""Reading of SAT certificates (.cer) and private keys (.key): renovación del gestor, fase 3.

There is no maintained Python library equivalent to phpcfdi/credentials, so this uses the standard X.509 and
PKCS#8 support of `cryptography`. Everything happens in memory: nothing here writes to disk or logs a secret.

What a SAT .cer carries (DER, PEM also accepted):
- holder name: subject `name` (2.5.4.41) or CN;
- RFC: subject x500UniqueIdentifier (2.5.4.45); for legal entities «RFC empresa / RFC representante»;
- CURP: subject serialNumber (2.5.4.5) when present (for legal entities, « / CURP representante»);
- certificate number: the serial number, whose bytes are the 20 ASCII digits of the number;
- CSD: an organizational unit (the branch) and a key usage without key agreement / data encipherment.
The dates of a certificate are not a validation before the SAT (no revocation is consulted).
"""

import hashlib
import re
import unicodedata

from cryptography import x509
from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
from cryptography.x509.oid import NameOID, ObjectIdentifier

UNIQUE_ID = ObjectIdentifier('2.5.4.45')
NAME = ObjectIdentifier('2.5.4.41')
RFC = re.compile(r'^[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}$')
SAT_ISSUER = 'SERVICIO DE ADMINISTRACION TRIBUTARIA'
MAX_FILE = 64 * 1024


class CertificateError(ValueError):
    """The file is not a SAT certificate, or the key does not open / does not match."""


def fold(text):
    text = unicodedata.normalize('NFD', text or '')
    return ''.join(c for c in text if unicodedata.category(c) != 'Mn').upper().strip()


def _attr(name, oid):
    values = name.get_attributes_for_oid(oid)
    return values[0].value if values else ''


def _split(value):
    """«AAA010101AAA / HEGT7610034S2» → ['AAA010101AAA', 'HEGT7610034S2']; empty parts dropped."""
    return [part.strip().upper() for part in str(value or '').split('/') if part.strip()]


def certificate_number(serial):
    """The SAT serial number is the ASCII text of the 20-digit number; anything else is shown in hex."""
    raw = serial.to_bytes((serial.bit_length() + 7) // 8 or 1, 'big')
    try:
        text = raw.decode('ascii')
    except UnicodeDecodeError:
        text = ''
    return text if text.isdigit() else format(serial, 'X')


def load_certificate(data):
    if not data or len(data) > MAX_FILE:
        raise CertificateError('El archivo no es un certificado válido del SAT.')
    try:
        if data.lstrip().startswith(b'-----BEGIN'):
            return x509.load_pem_x509_certificate(data)
        return x509.load_der_x509_certificate(data)
    except Exception:  # noqa: BLE001 - any parse failure means «not a certificate»
        raise CertificateError('El archivo no es un certificado válido del SAT.') from None


def detected_class(cert):
    """'CSD' or 'FIEL', from the branch (OU) and the key usage."""
    if cert.subject.get_attributes_for_oid(NameOID.ORGANIZATIONAL_UNIT_NAME):
        return 'CSD'
    try:
        usage = cert.extensions.get_extension_for_class(x509.KeyUsage).value
        if not usage.key_agreement and not usage.data_encipherment:
            return 'CSD'
    except x509.ExtensionNotFound:
        pass
    return 'FIEL'


def read_certificate(data):
    """Public data of a .cer. Raises CertificateError when the file cannot be read."""
    cert = load_certificate(data)
    subject, issuer = cert.subject, cert.issuer
    rfcs = _split(_attr(subject, UNIQUE_ID))
    curps = _split(_attr(subject, NameOID.SERIAL_NUMBER))
    issuer_org = fold(_attr(issuer, NameOID.ORGANIZATION_NAME))
    return {
        'holder_name': str(_attr(subject, NAME) or _attr(subject, NameOID.COMMON_NAME)).strip()[:300],
        'rfc': rfcs[0] if rfcs else '',
        'representative_rfc': rfcs[1] if len(rfcs) > 1 else '',
        'curp': curps[-1] if curps else '',
        'number': certificate_number(cert.serial_number),
        'serial': format(cert.serial_number, 'X'),
        'valid_from': cert.not_valid_before_utc,
        'valid_until': cert.not_valid_after_utc,
        'issuer': str(_attr(issuer, NameOID.COMMON_NAME) or issuer_org)[:300],
        'issued_by_sat': SAT_ISSUER in issuer_org,
        'detected': detected_class(cert),
        'branch': str(_attr(subject, NameOID.ORGANIZATIONAL_UNIT_NAME)).strip()[:200],
        'fingerprint': hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest(),
        'subject': subject.rfc4514_string()[:1000],
    }


def open_key(data, password):
    """The private key of an encrypted PKCS#8 .key (DER, PEM also accepted)."""
    if not data or len(data) > MAX_FILE:
        raise CertificateError('La contraseña no abre la clave privada.')
    secret = password.encode() if password else None
    try:
        if data.lstrip().startswith(b'-----BEGIN'):
            return serialization.load_pem_private_key(data, secret)
        return serialization.load_der_private_key(data, secret)
    except UnsupportedAlgorithm:
        raise CertificateError('El formato de esta clave privada no es compatible.') from None
    except (ValueError, TypeError):
        raise CertificateError('La contraseña no abre la clave privada.') from None


def key_matches(cert_data, key):
    """Same public key and a sign/verify round trip."""
    cert = load_certificate(cert_data)
    public = cert.public_key()
    der = serialization.Encoding.DER
    spki = serialization.PublicFormat.SubjectPublicKeyInfo
    if public.public_bytes(der, spki) != key.public_key().public_bytes(der, spki):
        return False
    probe = b'contasuite-key-check'
    try:
        if isinstance(key, rsa.RSAPrivateKey):
            public.verify(
                key.sign(probe, padding.PKCS1v15(), hashes.SHA256()), probe, padding.PKCS1v15(), hashes.SHA256()
            )
        elif isinstance(key, ec.EllipticCurvePrivateKey):
            public.verify(key.sign(probe, ec.ECDSA(hashes.SHA256())), probe, ec.ECDSA(hashes.SHA256()))
        else:
            return False
    except InvalidSignature:
        return False
    return True


def checks(cer, key, password, chosen, company_rfc, company_representative_rfc='', now=None):
    """The six checks of the spec. Returns (read data or None, [check…]); a check is
    {id, ok, message, blocking}. `chosen` is FIEL_EMPRESA, FIEL_REPRESENTANTE or CSD."""
    from .models import now as clock

    stamp = now or clock()
    out = []

    def add(ident, ok, message, blocking=True, **extra):
        out.append({'id': ident, 'ok': bool(ok), 'message': message, 'blocking': blocking, **extra})

    try:
        data = read_certificate(cer)
    except CertificateError as e:
        add('certificate', False, str(e))
        return None, out
    add(
        'certificate',
        data['issued_by_sat'],
        'Certificado del SAT leído.' if data['issued_by_sat'] else 'El archivo no es un certificado válido del SAT.',
    )
    private = None
    try:
        private = open_key(key, password)
        add('password', True, 'La contraseña abre la clave privada.')
    except CertificateError as e:
        add('password', False, str(e))
    if private is not None:
        matches = key_matches(cer, private)
        add(
            'pair',
            matches,
            'La clave privada corresponde al certificado.'
            if matches
            else 'La clave privada no corresponde a este certificado.',
        )
    else:
        add('pair', False, 'No se pudo comprobar sin abrir la clave privada.')
    expected = 'CSD' if chosen == 'CSD' else 'FIEL'
    suggestion = None
    if data['detected'] != expected:
        suggestion = 'CSD' if data['detected'] == 'CSD' else 'FIEL_EMPRESA'
    add(
        'class',
        data['detected'] == expected,
        f'Es {"un sello digital (CSD)" if data["detected"] == "CSD" else "una FIEL"}, como elegiste.'
        if data['detected'] == expected
        else f'El certificado parece {"un sello digital (CSD)" if data["detected"] == "CSD" else "una FIEL"}, '
        'no lo que elegiste.',
        suggestion=suggestion,
    )
    rfc = data['rfc']
    if chosen == 'FIEL_REPRESENTANTE':
        ok = len(rfc) == 13 and bool(RFC.match(rfc))
        message = (
            'RFC de persona física del representante.'
            if ok
            else 'La FIEL del representante debe ser de una persona física (RFC de 13 caracteres).'
        )
        if ok and company_representative_rfc and company_representative_rfc != rfc:
            ok, message = False, 'El RFC no coincide con el representante que trae la FIEL de la empresa.'
        add('rfc', ok, message)
    else:
        ok = rfc == (company_rfc or '').upper()
        add('rfc', ok, 'El RFC coincide con la empresa.' if ok else 'El RFC del certificado no es el de la empresa.')
    valid = data['valid_from'] <= stamp <= data['valid_until']
    add(
        'validity',
        valid,
        'Certificado vigente.' if valid else 'El certificado no está vigente: sólo se puede guardar como historial.',
        blocking=False,
    )
    return data, out
