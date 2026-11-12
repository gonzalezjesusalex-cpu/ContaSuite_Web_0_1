"""Explicit, inspectable service registration plan; no policy/network changes."""
import argparse,ctypes,json,re,subprocess,sys
from pathlib import Path
def probe():
    from ctypes import wintypes as w
    api=ctypes.WinDLL('advapi32',use_last_error=True)
    api.OpenSCManagerW.argtypes=[w.LPCWSTR,w.LPCWSTR,w.DWORD];api.OpenSCManagerW.restype=w.HANDLE
    api.CloseServiceHandle.argtypes=[w.HANDLE];api.CloseServiceHandle.restype=w.BOOL
    handle=api.OpenSCManagerW(None,None,2)
    result={'can_create_service':bool(handle),'winerror':0 if handle else ctypes.get_last_error(),'services_modified':False}
    if handle:api.CloseServiceHandle(handle)
    return result
def plan(root,name,data,logs,config,port):
    if not re.fullmatch(r'ContaSuite[A-Za-z0-9_]{0,40}',name):raise ValueError('Dedicated ContaSuite service name required')
    for p in (root,data,logs,config):
        if not p.is_absolute():raise ValueError('Absolute paths required')
    executable=root/'runtime/python.exe';script=root/'app/scripts/windows_service.py'
    binary=subprocess.list2cmdline([str(executable),'-B',str(script),'--name',name,'--data-dir',str(data),'--log-dir',str(logs),'--config-file',str(config),'--port',str(port)])
    return [['sc.exe','create',name,'binPath=',binary,'start=','auto','obj=','NT SERVICE\\'+name],
        ['sc.exe','sidtype',name,'unrestricted'],['sc.exe','failure',name,'reset=','86400','actions=','restart/15000/restart/30000/restart/60000'],
        ['sc.exe','failureflag',name,'1']]
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--probe',action='store_true');parser.add_argument('--apply',action='store_true')
    parser.add_argument('--root',type=Path);parser.add_argument('--name',default='ContaSuiteApi')
    parser.add_argument('--data-dir',type=Path);parser.add_argument('--log-dir',type=Path);parser.add_argument('--config-file',type=Path);parser.add_argument('--port',type=int,default=8000)
    args=parser.parse_args()
    if args.probe:print(json.dumps(probe()));return
    if not all([args.root,args.data_dir,args.log_dir,args.config_file]):parser.error('Explicit installation/data/log/config paths required')
    commands=plan(args.root,args.name,args.data_dir,args.log_dir,args.config_file,args.port)
    if not args.apply:print(json.dumps({'commands':commands,'applied':False},indent=2));return
    if not (args.root/'PACKAGE_SHA256.json').is_file():parser.error('Verified packaged installation required')
    # Refuse any existing service: never hijack/reconfigure another installation.
    query=subprocess.run(['sc.exe','query',args.name],capture_output=True)
    if query.returncode!=1060:parser.error('Service exists or cannot be inspected; refusing registration')
    for command in commands:subprocess.run(command,check=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    print('Service registered but not started. Provision private ACL/configuration before starting.')
if __name__=='__main__':main()
