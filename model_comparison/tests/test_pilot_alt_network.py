"""Targeted client proxy inheritance and unchanged CAD network isolation."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

TOOLS = Path(__file__).resolve().parents[1] / 'tools'
sys.path.insert(0, str(TOOLS))
from pilot_alt_network import client_environment, LOOPBACK


class ClientNetwork(unittest.TestCase):
    def test_environment_allowlist(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'network.json'
            path.write_text(json.dumps({'http_proxy_url': 'http://127.0.0.1:9'}))
            env = client_environment(path)
            self.assertEqual(set(env), {'PATH', 'HOME', 'LANG', 'http_proxy', 'https_proxy',
                                       'HTTP_PROXY', 'HTTPS_PROXY', 'no_proxy', 'NO_PROXY'})
            self.assertEqual(env['NO_PROXY'], LOOPBACK)
            self.assertEqual(env['https_proxy'], 'http://127.0.0.1:9')

    def test_reject_credentials_and_non_http_proxy(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'network.json'
            for value in ('http://synthetic:synthetic@localhost:9', 'http://localhost:9/?x=y',
                          'socks5://localhost:9', 'http://localhost:9/#fragment'):
                path.write_text(json.dumps({'http_proxy_url': value}))
                with self.assertRaises(ValueError):
                    client_environment(path)

    def test_actual_linux_client_child_and_cad_namespace(self):
        source = r'''
import json,os,subprocess,sys,tempfile
from pathlib import Path
base=Path('/home/camus/robotgen-alt-runtime/continuation_20260923_0332')
sys.path.insert(0,str(base/'operator'))
from pilot_alt_network import client_environment
from pilot_sandbox import execute_python
with tempfile.TemporaryDirectory(prefix='pilot-network-synthetic-') as folder:
 path=Path(folder)/'network.json'
 path.write_text(json.dumps({'http_proxy_url':'http://127.0.0.1:9'}))
 env=client_environment(path)
 code="import os,json; print(json.dumps({'proxy_received':all(os.environ.get(k)=='http://127.0.0.1:9' for k in ('http_proxy','https_proxy','HTTP_PROXY','HTTPS_PROXY')), 'no_proxy_exact':os.environ.get('NO_PROXY')=='localhost,127.0.0.1,::1', 'all_proxy_absent':not any(k in os.environ for k in ('ALL_PROXY','all_proxy'))}))"
 client=subprocess.run(['/usr/bin/python3','-I','-B','-c',code],env=env,capture_output=True,text=True,timeout=10)
 os.environ.update(env)
 os.environ['SYNTHETIC_NETWORK_TEST_SECRET']='SYNTHETIC_ONLY'
 cad_source="""import os,socket,json
names=('http_proxy','https_proxy','HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','all_proxy','NO_PROXY','no_proxy','SYNTHETIC_NETWORK_TEST_SECRET')
r={'proxy_and_synthetic_secret_absent':not any(k in os.environ for k in names),'home_is_tmp':os.environ.get('HOME')=='/tmp','blocked':{}}
for host,port in [('198.51.100.1',443),('127.0.0.1',7897)]:
 try:
  with socket.create_connection((host,port),timeout=1): pass
  r['blocked'][host]=False
 except OSError: r['blocked'][host]=True
print(json.dumps(r))
"""
 cad=execute_python(cad_source,kit=base/'public',cad=True,seconds=10)
 print(json.dumps({'client_exit_code':client.returncode,'client':json.loads(client.stdout),'cad_exit_code':cad.returncode,'cad':json.loads(cad.stdout)}))
'''
        argv = ['wsl', '-d', 'Ubuntu-24.04', '-u', 'camus', '--', '/usr/bin/python3', '-B', '-']
        child = subprocess.run(argv, input=source.encode(), capture_output=True, timeout=45)
        self.assertEqual(child.returncode, 0, 'Linux targeted verification failed')
        state = json.loads(child.stdout)
        record = TOOLS.parent / 'records/pilot_20260923/alternate_access_20260923/continuation_20260923_0332/network_fix_20260923/isolation_test.json'
        record.write_text(json.dumps(dict(state, argv=argv, outer_exit_code=child.returncode), indent=2)+'\n', encoding='utf-8')
        self.assertEqual(state['client_exit_code'], 0)
        self.assertTrue(all(state['client'].values()))
        self.assertEqual(state['cad_exit_code'], 0)
        self.assertTrue(state['cad']['proxy_and_synthetic_secret_absent'])
        self.assertTrue(state['cad']['home_is_tmp'])
        self.assertTrue(all(state['cad']['blocked'].values()))


if __name__ == '__main__':
    unittest.main()
