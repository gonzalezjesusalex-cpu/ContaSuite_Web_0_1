import argparse
import os
import threading
import time
import webbrowser
import subprocess
from pathlib import Path
from setup_windows import configure

root=Path(__file__).resolve().parents[1]
os.chdir(root)
parser=argparse.ArgumentParser();parser.add_argument('--portable',action='store_true');args=parser.parse_args()
configure(args.portable)
import sys
sys.path.insert(0,str(root/'backend'))
import uvicorn
worker=None
stopping=threading.Event()
lifecycle=threading.Lock()

def open_when_ready():
    global worker
    from urllib.request import urlopen
    for _ in range(60):
        if stopping.is_set():return
        try:
            with urlopen('http://127.0.0.1:8000/api/health',timeout=1):pass
            with lifecycle:
                if stopping.is_set():return
                worker=subprocess.Popen([sys.executable,'-m','app.storage.worker'],cwd=root/'backend',
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            webbrowser.open('http://127.0.0.1:8000');return
        except OSError:time.sleep(1)
threading.Thread(target=open_when_ready,daemon=True).start()
try:
    uvicorn.run('app.main:app',host='127.0.0.1',port=8000)
finally:
    with lifecycle:stopping.set()
    if worker is not None:
        worker.terminate()
        try:worker.wait(timeout=10)
        except subprocess.TimeoutExpired:worker.kill()
