"""Synthetic certificates shaped like the SAT ones (never real): issuer «SERVICIO DE ADMINISTRACION TRIBUTARIA», RFC in
x500UniqueIdentifier, CURP in serialNumber, a 20-digit certificate number, OU for the CSD branch and an encrypted
PKCS#8 .key. Real FIEL and CSD of the office still have to be tried on the office computer (spec, section 5)."""

from datetime import datetime, timedelta, timezone
from functools import lru_cache

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID, ObjectIdentifier

SAT = 'SERVICIO DE ADMINISTRACION TRIBUTARIA'


@lru_cache(maxsize=None)
def _key(seed):
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _ca(issuer_org=SAT):
    key = _key('ca:' + issuer_org)
    name = x509.Name(
        [
            x509.NameAttribute(NameOID.COMMON_NAME, 'AC SINTETICA DE PRUEBAS'),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, issuer_org),
        ]
    )
    return key, name


def pair(
    rfc='SSI260101AB1',
    representative_rfc='',
    curp='',
    name='SERVICIOS SINTETICOS SA DE CV',
    branch='',
    password='Llave-Sintetica-1',
    start=-10,
    end=365,
    number='30001000000500003416',
    issuer_org=SAT,
    seed=None,
):
    """(cer DER, key DER encrypted with `password`, private key)."""
    key = _key(seed or (rfc + branch + number))
    ca_key, ca_name = _ca(issuer_org)
    unique = rfc + (' / ' + representative_rfc if representative_rfc else '')
    subject = [
        x509.NameAttribute(NameOID.COMMON_NAME, name),
        x509.NameAttribute(ObjectIdentifier('2.5.4.41'), name),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, name),
        x509.NameAttribute(ObjectIdentifier('2.5.4.45'), unique),
    ]
    if curp:
        subject.append(x509.NameAttribute(NameOID.SERIAL_NUMBER, (' / ' + curp) if representative_rfc else curp))
    if branch:
        subject.append(x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, branch))
    csd = bool(branch)
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name(subject))
        .issuer_name(ca_name)
        .public_key(key.public_key())
        .serial_number(int.from_bytes(number.encode(), 'big'))
        .not_valid_before(now + timedelta(days=start))
        .not_valid_after(now + timedelta(days=end))
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=True,
                key_encipherment=False,
                data_encipherment=not csd,
                key_agreement=not csd,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .sign(ca_key, hashes.SHA256())
    )
    encrypted = key.private_bytes(
        serialization.Encoding.DER,
        serialization.PrivateFormat.PKCS8,
        serialization.BestAvailableEncryption(password.encode()),
    )
    return cert.public_bytes(serialization.Encoding.DER), encrypted, key
