#!/usr/bin/env python3
"""交互安装入口；不修改系统网络设置。"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
import urllib.error
import ssl
import http.client

HERE = Path(__file__).resolve().parent

def ask(prompt):
    return input(prompt).strip()

SUBSCRIPTION_UA = 'clash.meta'

def subscription_error(exc):
    """Only return fixed messages: exception strings can contain private URLs."""
    if isinstance(exc, urllib.error.HTTPError):
        reasons = {401: '订阅凭据无效或已过期', 403: '服务商拒绝访问，可能是 UA、IP 限制或防护验证',
                   404: '订阅地址不存在或已失效', 429: '请求过于频繁，请稍后重试'}
        return f'HTTP {exc.code}：' + reasons.get(exc.code, '服务商返回错误或重定向异常')
    reason = exc.reason if isinstance(exc, urllib.error.URLError) else exc
    if isinstance(reason, ssl.SSLCertVerificationError):
        return 'TLS 证书验证失败：检查系统时间、CA 证书和服务商证书'
    if isinstance(reason, ssl.SSLError):
        return 'TLS 握手失败：检查服务商 HTTPS 和网络连接'
    if isinstance(reason, socket.gaierror):
        return 'DNS 解析失败：检查服务器域名解析和网络'
    if isinstance(reason, (TimeoutError, socket.timeout)):
        return '连接或读取超时：服务器可能无法直连订阅站点'
    if isinstance(reason, ConnectionRefusedError):
        return '连接被拒绝：检查订阅站点或环境代理是否可用'
    if isinstance(reason, ValueError):
        return '链接无效或发生不安全重定向；请使用完整 HTTP(S) 订阅链接'
    return '网络请求失败：检查连接、环境代理和订阅站点可达性'

def subscription(choice=None):
    choice = choice or ask('A 输入订阅链接 / B 粘贴内容 / C 本地文件: ').upper()
    if choice == 'A':
        url = ask('订阅链接（不会保存）: ')
        if not url.startswith('https://'):
            if not url.startswith('http://') or ask('HTTP 未加密，继续请输入 YES: ') != 'YES':
                raise ValueError('已取消')
        class Redirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                if not newurl.startswith('https://') and not (url.startswith('http://') and newurl.startswith('http://')):
                    raise ValueError('拒绝不安全重定向')
                return super().redirect_request(req, fp, code, msg, headers, newurl)
        try:
            request = urllib.request.Request(url, headers={
                'User-Agent': SUBSCRIPTION_UA,
                'Accept': 'application/yaml, text/yaml, text/plain, */*',
                'Accept-Encoding': 'identity',
            })
            with urllib.request.build_opener(Redirect).open(request, timeout=30) as response:
                data = response.read(8 * 1024 * 1024 + 1)
                prefix = data.lstrip()[:256].lower()
                if 'text/html' in response.headers.get('Content-Type', '').lower() or prefix.startswith((b'<!doctype html', b'<html')):
                    print('订阅站点返回 HTML 网页，可能是登录页或防护验证页；请使用真正的订阅链接，或粘贴订阅内容。')
                    return subscription()
        except (OSError, ValueError, http.client.HTTPException) as exc:
            print('订阅获取失败：' + subscription_error(exc) + '。可重试或选择粘贴。')
            return subscription()
    elif choice == 'B':
        print('粘贴订阅，单独一行 . 结束：')
        lines = []
        while True:
            line = input()
            if line == '.': break
            lines.append(line)
            if sum(map(len, lines)) > 8 * 1024 * 1024: raise ValueError('订阅过大')
        data = '\n'.join(lines).encode()
    elif choice == 'C':
        with open(ask('文件路径: '), 'rb') as stream:
            data = stream.read(8 * 1024 * 1024 + 1)
    else:
        raise ValueError('无效选择')
    if not data or len(data) > 8 * 1024 * 1024: raise ValueError('订阅为空或超过 8 MiB')
    return data

def installer():
    spec = importlib.util.spec_from_file_location('installer', HERE / 'install.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def bundle(args):
    mod = installer()
    if args.bundle == 'offline':
        subprocess.run(['bash', str(HERE / 'install.sh'), '--download-only', '--arch', args.arch], check=True)
    names = list(json.loads((HERE / 'project-sha256.json').read_text())) + ['project-sha256.json', 'README.md', 'INSTALL.md', 'USAGE.md', 'CHANGELOG.md', 'LICENSE']
    if args.bundle == 'offline':
        names += ['assets/' + a['name'] for a in json.loads((HERE / 'assets.json').read_text())['assets'] if a.get('arch', args.arch) == args.arch]
    output = Path(args.output).resolve()
    with tarfile.open(output, 'w:gz') as archive:
        for name in sorted(set(names)):
            archive.add(HERE / name, arcname='mihomo-tui/' + name, recursive=False)
    Path(str(output) + '.sha256').write_text(mod.digest(output) + '  ' + output.name + '\n')
    print('软件包已生成:', output)

def choose_mirror():
    mirrors = ['https://ghfast.top', 'https://gh-proxy.com', 'https://gh-proxy.org']
    print('内核 Release 下载源（数据库使用独立来源，不能填入这里）：')
    print('0 默认回退顺序')
    for index, mirror in enumerate(mirrors, 1):
        print(f'{index} {mirror}')
    print('4 自定义 HTTPS 镜像根地址')
    while True:
        choice = ask('请选择编号 [0]: ') or '0'
        if choice == '0':
            return None
        if choice in ('1', '2', '3'):
            return mirrors[int(choice) - 1]
        if choice == '4':
            value = ask('镜像根地址，例如 https://ghfast.top（不是资源文件 URL）: ')
            parts = urllib.parse.urlsplit(value)
            if (parts.scheme == 'https' and parts.hostname and not parts.username
                    and not parts.password and parts.path in ('', '/')
                    and not parts.query and not parts.fragment):
                return value.rstrip('/')
            print('请输入 HTTPS 镜像根地址，不接受数据库、CDN 文件或完整下载链接。')
        else:
            print('请选择编号；不要粘贴测试结果中的资源 URL。')

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--wizard', action='store_true')
    p.add_argument('--bundle', choices=['light', 'offline'])
    p.add_argument('--arch', choices=['amd64', 'arm64'], default='amd64')
    p.add_argument('--output')
    args = p.parse_args()
    if args.bundle:
        if not args.output: p.error('需要 --output')
        return bundle(args)
    if not sys.stdin.isatty(): raise ValueError('向导需要终端；自动化请使用 --subscription 文件')
    print('Mihomo TUI 安装向导：本地 mixed，不修改路由、DNS、防火墙或全局代理。')
    mod = installer()
    if os.geteuid() != 0:
        raise RuntimeError('安装需要 root，请执行 sudo bash install.sh。')
    mod.dependencies(False, False)
    mod.compatible_service()
    offline = ask('1 在线安装（优先本地资源） / 2 严格离线: ') == '2'
    command = [sys.executable, str(HERE / 'install.py')]
    if offline: command.append('--offline')
    elif ask('测试下载来源？[y/N] ').lower() == 'y':
        manifest = json.loads((HERE / 'assets.json').read_text())
        arch = 'arm64' if os.uname().machine == 'aarch64' else 'amd64'
        for asset in [a for a in manifest['assets'] if a.get('arch', arch) == arch]:
            print(asset['name'])
            for url in mod.urls(asset, []):
                start = time.monotonic()
                result = subprocess.run(['curl', '-fLsS', '--range', '0-65535', '--max-filesize', '1048576', '--connect-timeout', '3', '--max-time', '5', '-o', os.devnull, '-w', '%{speed_download}', url], capture_output=True, text=True)
                print(('可用' if result.returncode == 0 else '失败'), round(time.monotonic()-start, 2), '秒', result.stdout, 'B/s', url)
        mirror = choose_mirror()
        if mirror: command += ['--mirror', mirror]
    fresh = not (mod.CONFIG / 'config.yaml').exists()
    if not fresh:
        print('检测到已有配置，保留现有配置和订阅。')
    if fresh:
        for port in (7890, 9090):
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', port))
    with tempfile.TemporaryDirectory(prefix='mnode-sub-') as temp:
        if fresh:
            path = Path(temp) / 'subscription'
            path.write_bytes(subscription())
            path.chmod(0o600)
            command += ['--subscription', str(path)]
        if ask('安装到 /usr/local/bin 和 /etc/mihomo；确认请输入 YES: ') != 'YES': return
        subprocess.run(command, check=True)
    if fresh and ask('启动本地 mixed 并验通？[y/N] ').lower() == 'y':
        subprocess.run([str(mod.BIN / 'mihomo-tui'), 'on'], check=True)
        if not mod.healthy():
            print('已安装，但服务/API 健康检查失败。请进入菜单检查。')
        else:
            result = subprocess.run(['curl', '-fLsS', '--proxy', 'http://127.0.0.1:7890', '--noproxy', '', '--connect-timeout', '5', '--max-time', '20', '-o', os.devnull, 'https://www.gstatic.com/generate_204'])
            print('代理 HTTPS 验通成功' if result.returncode == 0 else '已安装，代理未验通；可在管理菜单换节点或停止服务。')
            if result.returncode == 0 and ask('通过代理测试 GitHub 官方源？[y/N] ').lower() == 'y':
                subprocess.run(['curl', '-fLsS', '--proxy', 'http://127.0.0.1:7890', '--noproxy', '', '--max-time', '20', '-o', os.devnull, 'https://github.com'])
        if ask('启用开机自启？[y/N] ').lower() == 'y':
            subprocess.run(['systemctl', 'enable', 'mihomo'], check=True)
    if ask('进入管理菜单？[Y/n] ').lower() != 'n': subprocess.run([str(mod.BIN / 'mihomo-tui'), 'tui'], check=True)

if __name__ == '__main__':
    os.umask(0o077)
    try: main()
    except (EOFError, KeyboardInterrupt): print('\n已取消')
    except subprocess.CalledProcessError as exc:
        print(f'安装或子命令失败（退出码 {exc.returncode}），请查看上方具体原因；未进入后续菜单。', file=sys.stderr)
        sys.exit(1)
    except RuntimeError as exc:
        print('安装无法继续：' + str(exc), file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError:
        print('所需程序或项目文件不存在，请确认完整项目包和系统依赖已安装。', file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print('操作失败:', type(exc).__name__, file=sys.stderr)
        sys.exit(1)
