#!/bin/sh
exec /usr/bin/python3 -c 'import json,os,urllib.request
try:
    response=urllib.request.urlopen("http://192.168.100.106:8080/health",timeout=2)
    online=response.status==200
except OSError:
    online=False
print(json.dumps({"agent_installed":os.path.isfile("/usr/local/bin/lynx-agent"),"audit_log_present":os.path.isfile("/var/log/lynx-agent.jsonl"),"nexus_reachable":online}))'
