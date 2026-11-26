"""Master keyring of the password manager (plan v1.1, Cambio 4). Run by the operator, never at startup.

Since the renovación del gestor (fase 1, cs_0022) secrets are opened with the vault's master password, not with this
keyring. It is read only once, when an administrator creates the vault from the screen, to re-wrap the envelopes
sealed before; keep it (and its offline backup) until that is done and checked on the office computer.

The keyring is protected with Windows DPAPI and written to <data-dir>/vault/keyring.dpapi; it never goes to the
database, to .env or to the repository. Without it a database backup does not recover any secret, so make the
offline backup right after creating it and keep it apart (USB in a safe, printed sheet…).

  --init                 create a new keyring (refuses to replace an existing one)
  --machine              protect for the machine (any account of this Windows can open it: use it when the
                         service runs under another account); default: only the current Windows user
  --backup FILE          write the keys in clear to FILE for the offline backup (then move FILE off this computer)
  --restore FILE         rebuild the DPAPI keyring from an offline backup on a new server
  --rotate               add a new active key; earlier keys stay to open existing secrets
  --status               say whether the keyring opens (never prints keys)
"""

import argparse
import base64
import json
import os
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-dir', type=Path, required=True)
    parser.add_argument('--init', action='store_true')
    parser.add_argument('--machine', action='store_true')
    parser.add_argument('--backup', type=Path)
    parser.add_argument('--restore', type=Path)
    parser.add_argument('--rotate', action='store_true')
    parser.add_argument('--status', action='store_true')
    args = parser.parse_args()
    if os.name != 'nt':
        parser.error('DPAPI sólo existe en Windows.')
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
    from app.credential_crypto import VaultCipher, keyring_path, read_keyring, write_keyring

    path = keyring_path(args.data_dir)
    if args.init:
        if path.exists():
            parser.error('Ya existe un llavero; no se reemplaza (usa --rotate o borra a mano con respaldo).')
        keys, active = {'k1': os.urandom(32)}, 'k1'
        write_keyring(keys, active, args.data_dir, args.machine)
        print('Llavero creado:', path)
        print('Haz ahora el respaldo fuera de línea con --backup y guárdalo lejos de este equipo.')
    if args.restore:
        if path.exists():
            parser.error('Ya existe un llavero en este equipo; no se reemplaza.')
        data = json.loads(args.restore.read_text(encoding='utf-8'))
        keys = {k: base64.b64decode(v, validate=True) for k, v in data['keys'].items()}
        VaultCipher(keys, data['active'])
        write_keyring(keys, data['active'], args.data_dir, args.machine)
        print('Llavero restaurado:', path)
    if args.rotate:
        keys, active = read_keyring(args.data_dir)
        new = 'k' + str(max(int(k[1:]) for k in keys if k[1:].isdigit()) + 1)
        keys[new] = os.urandom(32)
        write_keyring(keys, new, args.data_dir, args.machine)
        print('Nueva llave activa:', new, '- actualiza el respaldo fuera de línea.')
    if args.backup:
        if args.backup.exists():
            parser.error('El archivo de respaldo ya existe; elige otro nombre.')
        keys, active = read_keyring(args.data_dir)
        payload = {'active': active, 'keys': {k: base64.b64encode(v).decode() for k, v in keys.items()}}
        args.backup.write_text(json.dumps(payload), encoding='utf-8')
        print('Respaldo escrito en', args.backup, '- muévelo fuera de este equipo y bórralo de aquí.')
    if args.status:
        try:
            keys, active = read_keyring(args.data_dir)
            VaultCipher(keys, active)
            print('Llavero disponible; llave activa', active, '·', len(keys), 'llave(s).')
        except Exception:  # noqa: BLE001 - status only says whether it opens, never why in detail
            print('El llavero no abre con esta cuenta de Windows o no existe:', path)
            return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
