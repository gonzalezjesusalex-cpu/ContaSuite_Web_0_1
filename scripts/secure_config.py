"""Windows DPAPI machine-protected service configuration. Restrict the file ACL as well."""

import argparse
import base64
import ctypes
import json
import os
import getpass
import secrets
from pathlib import Path


def crypt(data, decrypt=False):
    if os.name != 'nt':
        raise RuntimeError('Windows DPAPI required')
    from ctypes import wintypes as w

    class Blob(ctypes.Structure):
        _fields_ = [('size', w.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]

    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    output = Blob()
    api = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    if decrypt:
        fn = api.CryptUnprotectData
        fn.argtypes = [
            ctypes.POINTER(Blob),
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
            w.DWORD,
            ctypes.POINTER(Blob),
        ]
        ok = fn(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output))
    else:
        fn = api.CryptProtectData
        fn.argtypes = [
            ctypes.POINTER(Blob),
            w.LPCWSTR,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
            w.DWORD,
            ctypes.POINTER(Blob),
        ]
        ok = fn(ctypes.byref(source), 'ContaSuite service configuration', None, None, None, 5, ctypes.byref(output))
    if not ok:
        raise RuntimeError('DPAPI operation failed')
    try:
        return ctypes.string_at(output.data, output.size)
    finally:
        kernel.LocalFree(output.data)


def load(path):
    values = json.loads(path.read_text(encoding='utf-8-sig'))
    if isinstance(values, dict) and values.get('format') == 'contasuite-dpapi-machine-v1':
        values = json.loads(crypt(base64.b64decode(values['protected'], validate=True), True))
    return values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--create', type=Path, required=True)
    args = parser.parse_args()
    path = args.create
    if not path.is_absolute() or path.exists():
        parser.error('Use a new absolute configuration filename')
    from sqlalchemy.engine import make_url

    database = getpass.getpass('DATABASE_URL PostgreSQL (oculta): ')
    url = make_url(database)
    if url.get_backend_name() != 'postgresql':
        parser.error('PostgreSQL required')
    hostname = input('Nombre DNS interno autorizado: ').strip()
    if not hostname or any(c in hostname for c in '/:* '):
        parser.error('DNS hostname required')
    token = secrets.token_urlsafe(48)
    values = {
        'DATABASE_URL': database,
        'APP_TOKEN': token,
        'AGENT_TOKEN': secrets.token_urlsafe(48),
        'CS_ALLOWED_HOSTS': json.dumps(['localhost', '127.0.0.1', hostname]),
        'CS_STORAGE_ALLOWED_ROOTS': '[]',
        'CS_STORAGE_SMB_ALLOWED_ROOTS': '[]',
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        json.dump(
            {
                'format': 'contasuite-dpapi-machine-v1',
                'protected': base64.b64encode(crypt(json.dumps(values).encode())).decode('ascii'),
            },
            stream,
        )
    print('Configuración protegida creada. Restringir ACL a SYSTEM, administradores y cuenta del servicio.')
    print('Clave de alta inicial (guardar en el gestor de secretos): ' + token)


if __name__ == '__main__':
    main()
