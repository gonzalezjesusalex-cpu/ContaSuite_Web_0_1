// Development launcher: Vite and FastAPI share one process lifecycle.
import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const python=process.env.CONTA_PYTHON||path.join(root,'.venv',process.platform==='win32'?'Scripts/python.exe':'bin/python');
if(!existsSync(python)){console.error('Primero prepara .venv con backend/requirements.txt y configura .env.');process.exit(1)}
const api=spawn(python,['-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8000'],{cwd:path.join(root,'backend'),stdio:'inherit'});
const vite=spawn(process.execPath,[path.join(root,'frontend/node_modules/vite/bin/vite.js'),'--host','127.0.0.1','--port','4173'],{cwd:path.join(root,'frontend'),stdio:'inherit'});
let worker;let startingWorker=false;
const workerTimer=setInterval(async()=>{if(startingWorker)return;startingWorker=true;try{const response=await fetch('http://127.0.0.1:8000/api/health');if(response.ok){clearInterval(workerTimer);worker=spawn(python,['-m','app.storage.worker'],{cwd:path.join(root,'backend'),stdio:'inherit',windowsHide:true})}}catch{}finally{startingWorker=false}},1000);
let ending=false;const stop=(code=0)=>{if(ending)return;ending=true;clearInterval(workerTimer);worker?.kill();api.kill();vite.kill();process.exit(code)};
api.on('exit',code=>stop(code||0));vite.on('exit',code=>stop(code||0));process.on('SIGINT',()=>stop());process.on('SIGTERM',()=>stop());
