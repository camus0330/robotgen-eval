"""Process-only network settings for the official Linux Codex client."""
import argparse
import json
from pathlib import Path
import socket
import subprocess
import time
from urllib.parse import urlsplit

CLIENT = '/home/camus/robotgen-alt-client-20260923/codex-x86_64-unknown-linux-musl'
CONFIG = Path(__file__).with_name('client_network.json')
LOOPBACK = 'localhost,127.0.0.1,::1'
TARGETS = ('https://auth.openai.com/', 'https://chatgpt.com/')


def client_environment(config_path=None):
    data = json.loads(Path(config_path or CONFIG).read_text(encoding='utf-8'))
    value = data['http_proxy_url']
    url = urlsplit(value)
    if (url.scheme != 'http' or not url.hostname or not url.port or
            url.username is not None or url.password is not None or
            url.path or url.query or url.fragment or any(c.isspace() for c in value)):
        raise ValueError('expected a credential-free HTTP proxy origin')
    # No inherited credentials, ALL_PROXY, wildcard NO_PROXY, or startup variables.
    env = {'PATH': '/usr/bin:/bin', 'HOME': '/home/camus', 'LANG': 'C.UTF-8'}
    env.update({name: value for name in ('http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY')})
    env.update(no_proxy=LOOPBACK, NO_PROXY=LOOPBACK)
    return env


def check(config_path=None):
    env = client_environment(config_path)
    proxy = urlsplit(env['https_proxy'])
    start = time.monotonic()
    try:
        with socket.create_connection((proxy.hostname, proxy.port), timeout=5):
            pass
        port = {'reachable': True, 'elapsed_s': time.monotonic() - start}
    except OSError as error:
        port = {'reachable': False, 'error_class': type(error).__name__,
                'elapsed_s': time.monotonic() - start}
    rows = []
    for target in TARGETS if port['reachable'] else ():
        argv = ['/usr/bin/curl', '--disable', '--silent', '--show-error',
                '--connect-timeout', '5', '--max-time', '20', '--retry', '0',
                '--output', '/dev/null', '--write-out',
                '%{http_connect}|%{http_code}|%{ssl_verify_result}|%{time_appconnect}|%{time_total}', target]
        child = subprocess.run(argv, env=env, capture_output=True, text=True, timeout=25)
        fields = child.stdout.strip().split('|')
        row = {'target': target, 'argv': argv, 'os_exit_code': child.returncode,
               'response_body_saved': False, 'authorization_sent': False}
        if len(fields) == 5:
            row.update(connect_http_status=int(fields[0]), http_status=int(fields[1]),
                       tls_verify_result=int(fields[2]), tls_elapsed_s=float(fields[3]),
                       elapsed_s=float(fields[4]))
            row['transport_pass'] = (child.returncode == 0 and row['connect_http_status'] == 200
                                     and row['tls_verify_result'] == 0 and row['http_status'] > 0)
        else:
            row['transport_pass'] = False
        # Curl errors have no headers/body; retain only an exit-code failure layer.
        row['failure_stage'] = None if row['transport_pass'] else {
            5: 'PROXY_DNS', 6: 'TARGET_DNS', 7: 'TCP_CONNECT', 28: 'TIMEOUT',
            35: 'TLS_HANDSHAKE', 60: 'CERTIFICATE_VERIFY', 56: 'CONNECT_OR_RECEIVE'
        }.get(child.returncode, 'TRANSPORT')
        rows.append(row)
    result = {'proxy': {'scheme': proxy.scheme, 'host': proxy.hostname, 'port': proxy.port},
              'port': port, 'targets': rows, 'model_requests': 0,
              'transport_pass': port['reachable'] and len(rows) == len(TARGETS)
                                and all(r['transport_pass'] for r in rows)}
    print(json.dumps(result))
    return 0 if result['transport_pass'] else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('check', 'login', 'login-status'))
    parser.add_argument('--config', type=Path)
    args = parser.parse_args()
    if args.action == 'check':
        return check(args.config)
    env = client_environment(args.config)
    if args.action == 'login':
        # Interactive user terminal only: do not capture or persist device codes.
        return subprocess.call([CLIENT, 'login', '--device-auth'], env=env)
    child = subprocess.run([CLIENT, 'login', 'status'], env=env, capture_output=True, timeout=20)
    print(json.dumps({'official_login_status_exit_code': child.returncode,
                      'authenticated': child.returncode == 0,
                      'network_verified_by_status': False}))
    return child.returncode


if __name__ == '__main__':
    raise SystemExit(main())
