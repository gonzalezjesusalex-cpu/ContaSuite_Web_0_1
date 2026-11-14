"""Recycled, memory-limited extractor protocol. Stdout contains structured metadata only."""

import sys
import json
import base64
from .storage.classify_process import memory_limit


def main():
    guard = memory_limit()
    from .pilot_extract import analyze

    for _ in range(100):
        line = sys.stdin.buffer.readline(36 * 1024 * 1024)
        if not line:
            return
        try:
            value = json.loads(line)
            result = analyze(base64.b64decode(value['content'], validate=True), value['name'])
            result['identities'] = result.get('identities', [])[:100]
            print(json.dumps(result), flush=True)
        except Exception:  # noqa: BLE001 - subprocess protocol: failure is reported to the parent as type unknown
            print(
                json.dumps(
                    {
                        'type': 'unknown',
                        'period': None,
                        'identities': [],
                        'evidence': {'readable': False, 'complete': False, 'rfcs': [], 'reason': 'extraction_failed'},
                    }
                ),
                flush=True,
            )


if __name__ == '__main__':
    main()
