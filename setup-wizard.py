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

HERE = Path(__file__).resolve().parent

def ask(prompt):
    return input(prompt).strip()

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
            with urllib.request.build_opener(Redirect).open(url, timeout=30) as response:
                data = response.read(8 * 1024 * 1024 + 1)
        except Exception:
            print('订阅获取失败，请重试或选择粘贴。')
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
    offline = ask('1 在线安装（优先本地资源） / 2 严格离线: ') == '2'
    command = ['bash', str(HERE / 'install.sh')]
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
        mirror = ask('优先 Release 镜像 HTTPS 地址（空则默认顺序）: ')
        if mirror: command += ['--mirror', mirror]
    fresh = not Path('/etc/mihomo/config.yaml').exists()
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
        subprocess.run(['mihomo-tui', 'on'], check=True)
        if not mod.healthy():
            print('已安装，但服务/API 健康检查失败。请进入菜单检查。')
        else:
            result = subprocess.run(['curl', '-fLsS', '--proxy', 'http://127.0.0.1:7890', '--noproxy', '', '--connect-timeout', '5', '--max-time', '20', '-o', os.devnull, 'https://www.gstatic.com/generate_204'])
            print('代理 HTTPS 验通成功' if result.returncode == 0 else '已安装，代理未验通；可在管理菜单换节点或停止服务。')
            if result.returncode == 0 and ask('通过代理测试 GitHub 官方源？[y/N] ').lower() == 'y':
                subprocess.run(['curl', '-fLsS', '--proxy', 'http://127.0.0.1:7890', '--noproxy', '', '--max-time', '20', '-o', os.devnull, 'https://github.com'])
        if ask('启用开机自启？[y/N] ').lower() == 'y':
            subprocess.run(['systemctl', 'enable', 'mihomo'], check=True)
    if ask('进入管理菜单？[Y/n] ').lower() != 'n': subprocess.run(['mihomo-tui', 'tui'])

if __name__ == '__main__':
    os.umask(0o077)
    try: main()
    except (EOFError, KeyboardInterrupt): print('\n已取消')
    except Exception as exc:
        print('操作失败:', type(exc).__name__, file=sys.stderr)
        sys.exit(1)
