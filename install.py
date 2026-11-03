#!/usr/bin/env python3
"""固定资源安装器；只使用标准库及系统已有命令。"""
import argparse
import fcntl
import gzip
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time

HERE = Path(__file__).resolve().parent
BIN = Path('/usr/local/bin')
CONFIG = Path('/etc/mihomo')
UNIT = Path('/etc/systemd/system/mihomo.service')
PROJECT = ('mihomo-tui', 'mnode', 'build-config.py', 'mnode-tui.py', 'setup-wizard.py')
SERVICE = '''[Unit]
Description=mihomo proxy
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/local/bin/mihomo -d /etc/mihomo -f /etc/mihomo/config.yaml
Restart=on-failure

[Install]
WantedBy=multi-user.target
'''


def run(*args, check=True, **kwargs):
    return subprocess.run([str(a) for a in args], check=check, **kwargs)


def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def valid(path, expected):
    return path.is_file() and digest(path) == expected


def urls(asset, mirrors):
    if 'github_path' in asset:
        return [f'https://{host}/gh/{asset["github_path"]}' for host in
                ('cdn.jsdelivr.net', 'testingcf.jsdelivr.net', 'gcore.jsdelivr.net', 'fastly.jsdelivr.net')] + [asset['url']]
    return [m.rstrip('/') + '/' + asset['url'] for m in
            mirrors + ['https://ghfast.top', 'https://gh-proxy.com', 'https://gh-proxy.org']] + [asset['url']]


def fetch(asset, directory, offline, mirrors):
    target = directory / asset['name']
    if valid(target, asset['sha256']):
        print(f'使用已校验本地资源: {target.name}')
        return target
    if not offline:
        # 每个资源总预算 180 秒，每个源一次尝试，最多 8 个源。
        deadline = time.monotonic() + 180
        for url in urls(asset, mirrors)[:8]:
            remaining = int(deadline - time.monotonic())
            if remaining <= 0:
                break
            fd, name = tempfile.mkstemp(prefix='.download-', dir=directory)
            os.close(fd)
            candidate = Path(name)
            try:
                print(f'下载 {asset["name"]}: {url}', flush=True)
                result = run('curl', '-fLsS', '--proto', '=https', '--proto-redir', '=https',
                             '--connect-timeout', '8', '--max-time', str(min(45, remaining)),
                             '-o', candidate, url, check=False)
                if result.returncode == 0 and valid(candidate, asset['sha256']):
                    os.replace(candidate, target)
                    return target
                print('该来源失败或 SHA-256 不匹配，尝试下一个来源。')
            finally:
                candidate.unlink(missing_ok=True)
    raise RuntimeError(f'离线补齐: {target}\n  来源: {asset["url"]}\n  SHA-256: {asset["sha256"]}')


def dependencies(offline, download_only):
    required = ['curl'] if not offline else []
    if not download_only:
        required += ['bash', 'curl', 'systemctl', 'flock', 'unshare']
        if not Path('/run/systemd/system').is_dir():
            raise RuntimeError('需要正在运行 systemd 的 Debian/Ubuntu 或 RHEL 系环境。')
        values = {}
        for line in Path('/etc/os-release').read_text().splitlines():
            if '=' in line:
                key, value = line.split('=', 1)
                values[key] = value.strip('"')
        family = (values.get('ID', '') + ' ' + values.get('ID_LIKE', '')).split()
        if not set(family) & {'debian', 'ubuntu', 'rhel', 'fedora', 'centos', 'rocky', 'almalinux'}:
            raise RuntimeError('仅支持 Debian/Ubuntu 和 RHEL 系。')
    missing = [name for name in required if not shutil.which(name)]
    if missing:
        raise RuntimeError('缺少依赖: ' + ', '.join(missing) +
                           '\nDebian/Ubuntu: apt install bash python3 curl ca-certificates util-linux systemd'
                           '\nRHEL: dnf install bash python3 curl ca-certificates util-linux systemd')


def atomic_copy(source, target, mode):
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.mnode-', dir=target.parent)
    os.close(fd)
    try:
        shutil.copyfile(source, name)
        os.chmod(name, mode)
        os.replace(name, target)
    finally:
        Path(name).unlink(missing_ok=True)


def active():
    return run('systemctl', 'is-active', '--quiet', 'mihomo', check=False).returncode == 0


def healthy():
    for _ in range(10):
        if active():
            args = ['curl', '-fsS', '--connect-timeout', '1', '--max-time', '2']
            if os.environ.get('MIHOMO_SECRET'):
                args += ['-H', 'Authorization: Bearer ' + os.environ['MIHOMO_SECRET']]
            args += [os.environ.get('MIHOMO_API', 'http://127.0.0.1:9090') + '/version']
            result = run(*args, check=False, stdout=subprocess.PIPE)
            try:
                if result.returncode == 0 and json.loads(result.stdout).get('version'):
                    return True
            except (ValueError, AttributeError):
                pass
        time.sleep(1)
    return False


def compatible_service():
    result = run('systemctl', 'show', 'mihomo', '--property=LoadState', '--value',
                 stdout=subprocess.PIPE, text=True)
    if result.stdout.strip() == 'not-found':
        return False
    result = run('systemctl', 'show', 'mihomo', '--property=ExecStart', '--value',
                 stdout=subprocess.PIPE, text=True)
    # Fail closed for custom arguments/paths, including overriding drop-ins.
    expected = 'argv[]=/usr/local/bin/mihomo -d /etc/mihomo -f /etc/mihomo/config.yaml ;'
    if expected not in result.stdout or 'path=/usr/local/bin/mihomo ;' not in result.stdout:
        raise RuntimeError('现有 mihomo 服务路径/参数不兼容，请先人工核对 systemctl cat mihomo。')
    return True


def install(opts, assets, manifest):
    CONFIG.mkdir(parents=True, exist_ok=True, mode=0o700)
    BIN.mkdir(parents=True, exist_ok=True)
    with open(CONFIG / '.mnode.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        has_service = compatible_service()
        was_active = active()
        fresh = not (CONFIG / 'config.yaml').exists()
        if fresh and not opts.subscription:
            raise RuntimeError('首次安装必须指定 --subscription 本地文件。')
        with tempfile.TemporaryDirectory(prefix='.install-', dir=CONFIG) as temp:
            stage = Path(temp)
            kernel = stage / 'mihomo'
            with gzip.open(assets[0], 'rb') as source, kernel.open('wb') as dest:
                shutil.copyfileobj(source, dest)
            kernel.chmod(0o755)
            # Preserve all local databases for validation of existing configurations.
            for path in CONFIG.iterdir():
                if path.is_file() and path.suffix in ('.dat', '.metadb', '.mmdb'):
                    shutil.copyfile(path, stage / path.name)
            geo_target = CONFIG / 'geoip.metadb'
            if opts.upgrade or not geo_target.exists():
                shutil.copyfile(assets[1], stage / 'geoip.metadb')
            if fresh:
                shutil.copyfile(opts.subscription, stage / 'sub.b64')
                run(sys.executable, HERE / 'build-config.py', '--mode', 'mixed',
                    '--subscription', stage / 'sub.b64', '--output', stage / 'config.yaml')
            else:
                shutil.copyfile(CONFIG / 'config.yaml', stage / 'config.yaml')
            selected_kernel = kernel if opts.upgrade or not (BIN / 'mihomo').exists() else BIN / 'mihomo'
            # Every validation uses a network namespace: no hidden geo downloads,
            # including in an existing user configuration or in --offline mode.
            run('unshare', '--net', '--', selected_kernel, '-d', stage, '-f', stage / 'config.yaml', '-t')
            changes = [(kernel, BIN / 'mihomo', 0o755),
                       (assets[1], geo_target, 0o600)]
            changes += [(path, CONFIG / 'vendor' / path.relative_to(HERE / 'vendor'), 0o644) for path in (HERE / 'vendor').rglob('*.py')]
            changes += [(HERE / name, BIN / name if name in ('mnode', 'mihomo-tui') else CONFIG / name,
                         0o755 if name in ('mnode', 'mihomo-tui') else 0o600) for name in PROJECT]
            # Menu must be readable by the invoking (non-root) user.
            changes = [(src, dst, 0o644 if dst.name in ('mnode-tui.py', 'setup-wizard.py') else mode)
                       for src, dst, mode in changes]
            if fresh:
                changes += [(stage / name, CONFIG / name, 0o600) for name in ('config.yaml', 'sub.b64')]
            if not has_service:
                (stage / 'mihomo.service').write_text(SERVICE)
                changes += [(stage / 'mihomo.service', UNIT, 0o644)]
            changes = [(src, dst, mode) for src, dst, mode in changes if opts.upgrade or not dst.exists()]
            backup = Path(tempfile.mkdtemp(prefix='backup-', dir=CONFIG))
            record = []
            for index, (_, dest, _) in enumerate(changes):
                saved = backup / str(index)
                exists = dest.exists()
                if exists:
                    shutil.copy2(dest, saved)
                record.append({'path': str(dest), 'saved': str(saved) if exists else None})
            (backup / 'receipt.json').write_text(json.dumps({'active': was_active, 'files': record}, indent=2))
            try:
                for source, dest, mode in changes:
                    atomic_copy(source, dest, mode)
                # Directory traversal allows unprivileged menu access; secrets stay 0600.
                CONFIG.chmod(0o755)
                for name in ('config.yaml', 'sub.b64'):
                    if (CONFIG / name).exists():
                        (CONFIG / name).chmod(0o600)
                run('systemctl', 'daemon-reload')
                if was_active and changes:
                    run('systemctl', 'restart', 'mihomo')
                    if not healthy():
                        raise RuntimeError('重启后 API 健康检查失败')
            except BaseException:
                for item in reversed(record):
                    dest = Path(item['path'])
                    if item['saved']:
                        saved = Path(item['saved'])
                        atomic_copy(saved, dest, saved.stat().st_mode & 0o777)
                    else:
                        dest.unlink(missing_ok=True)
                run('systemctl', 'daemon-reload', check=False)
                result = run('systemctl', 'restart' if was_active else 'stop', 'mihomo', check=False)
                print(f'已恢复文件；服务恢复命令退出码 {result.returncode}。备份: {backup}', file=sys.stderr)
                raise
            print(f'安装完成。备份及恢复清单: {backup}')
            if not was_active:
                print('服务保持停止；需要时执行 mihomo-tui on。未启用开机启动。')


def main():
    parser = argparse.ArgumentParser(description='mihomo 固定版本安装/离线部署')
    parser.add_argument('--assets-dir', type=Path, default=HERE / 'assets')
    parser.add_argument('--offline', action='store_true')
    parser.add_argument('--subscription', type=Path)
    parser.add_argument('--upgrade', action='store_true')
    parser.add_argument('--download-only', action='store_true')
    parser.add_argument('--arch', choices=('amd64', 'arm64'))
    parser.add_argument('--project-ref', help='补齐项目脚本的完整 40 位 Git 提交 SHA')
    parser.add_argument('--mirror', action='append', default=[])
    opts = parser.parse_args()
    os.umask(0o077)
    host_arch = {'x86_64': 'amd64', 'aarch64': 'arm64'}.get(platform.machine())
    arch = opts.arch or host_arch
    if not arch or (not opts.download_only and arch != host_arch):
        parser.error('架构不支持或与本机不符；跨架构准备请使用 --download-only --arch。')
    if opts.project_ref and not re.fullmatch(r'[0-9a-f]{40}', opts.project_ref):
        parser.error('--project-ref 需要完整的小写提交 SHA')
    if len(opts.mirror) > 4:
        parser.error('最多添加 4 个 --mirror，以保证预算内保留官方回退。')
    if any(not url.startswith('https://') for url in opts.mirror):
        parser.error('--mirror 必须使用 https://')
    if not opts.download_only and os.geteuid() != 0:
        parser.error('安装需要 root，请使用 sudo bash install.sh …')
    dependencies(opts.offline, opts.download_only)
    manifest = json.loads((HERE / 'assets.json').read_text())
    # The locally supplied project bundle is verified before execution/installation.
    sums = json.loads((HERE / 'project-sha256.json').read_text())
    for name, expected in sums.items():
        if Path(name).is_absolute() or '..' in Path(name).parts:
            raise RuntimeError('项目校验清单含有无效路径')
        if not valid(HERE / name, expected):
            if name not in PROJECT or not opts.project_ref:
                raise RuntimeError(f'项目文件缺失或校验失败: {HERE / name}；请获取同版完整项目文件，或用 --project-ref 补齐运行脚本。')
            asset = {'name': name, 'sha256': expected,
                     'github_path': f'esojourn/mihomo-tui@{opts.project_ref}/{name}',
                     'url': f'https://raw.githubusercontent.com/esojourn/mihomo-tui/{opts.project_ref}/{name}'}
            fetch(asset, HERE, opts.offline, [])
    opts.assets_dir.mkdir(parents=True, exist_ok=True)
    selected = [a for a in manifest['assets'] if a.get('arch', arch) == arch]
    assets, failures = [], []
    for asset in selected:
        try:
            assets.append(fetch(asset, opts.assets_dir, opts.offline, opts.mirror))
        except RuntimeError as exc:
            failures.append(str(exc))
    if failures:
        raise RuntimeError('\n'.join(failures))
    if opts.download_only:
        print('资源准备完成；请连同完整项目文件和本地订阅上传到目标机器。')
    else:
        install(opts, assets, manifest)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f'安装失败: {exc}', file=sys.stderr)
        sys.exit(1)
