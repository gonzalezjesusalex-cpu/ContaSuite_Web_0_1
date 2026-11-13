"""Agent lifecycle bound to this installation, using its encrypted service configuration."""
import importlib.util,json
from pathlib import Path
from datetime import datetime,timezone
from local_setup import marker
from secure_config import load

def run_agent(root,stop_event):
    values=marker(root);private=load(root/'private/service.json')
    activation=root/'private/agent-activation.json'
    if not activation.exists():
        with activation.open('x',encoding='utf-8') as stream:json.dump({'not_before':datetime.now(timezone.utc).isoformat()},stream)
    cutoff=json.loads(activation.read_text(encoding='utf-8'))['not_before']
    spec=importlib.util.spec_from_file_location('contasuite_windows_agent',root/'app/agent/agent.py')
    agent=importlib.util.module_from_spec(spec);spec.loader.exec_module(agent)
    agent.run({'api_url':'http://127.0.0.1:'+str(values['api_port']),'agent_id':'windows-'+values['database'][-12:],
        'token':private['AGENT_TOKEN'],'allowed_roots':json.loads(private['CS_STORAGE_ALLOWED_ROOTS']),'not_before':cutoff},stop_event)
