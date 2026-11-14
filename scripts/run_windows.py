import argparse
import os
import threading
import time
import webbrowser
import subprocess
from pathlib import Path
from setup_windows import configure, launcher_port

root = Path(__file__).resolve().parents[1]
os.chdir(root)
parser = argparse.ArgumentParser()
parser.add_argument('--portable', action='store_true')
args = parser.parse_args()
port = launcher_port()
configure(args.portable)
base_url = f'http://127.0.0.1:{port}'
import sys

sys.path.insert(0, str(root / 'backend'))
import uvicorn

worker = None
stopping = threading.Event()
lifecycle = threading.Lock()


def open_when_ready():
    global worker
    from urllib.request import urlopen

    for _ in range(60):
        if stopping.is_set():
            return
        try:
            with urlopen(base_url + '/api/health', timeout=1):
                pass
            with lifecycle:
                if stopping.is_set():
                    return
                worker = subprocess.Popen(
                    [sys.executable, '-m', 'app.storage.worker'],
                    cwd=root / 'backend',
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                )
            webbrowser.open(base_url)
            return
        except OSError:
            time.sleep(1)


threading.Thread(target=open_when_ready, daemon=True).start()
try:
    uvicorn.run('app.main:app', host='127.0.0.1', port=port)
finally:
    with lifecycle:
        stopping.set()
    if worker is not None:
        worker.terminate()
        try:
            worker.wait(timeout=10)
        except subprocess.TimeoutExpired:
            worker.kill()
