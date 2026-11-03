#!/usr/bin/env python3
"""隔离回归测试：不接触系统服务或路由。python3 test-mnode.py"""
import base64
import contextlib
import gzip
import fcntl
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / (name + '.py'))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


installer = module('install')
builder = module('build-config')
tui = module('mnode-tui')


class Downloads(unittest.TestCase):
    def test_fallback_and_offline(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            asset = dict(name='kernel.gz', sha256=hashlib.sha256(b'valid').hexdigest(),
                         url='https://github.com/test/file')
            calls = []

            def fake(*args, **kwargs):
                calls.append(args)
                Path(args[args.index('-o') + 1]).write_bytes(
                    b'<html>error</html>' if len(calls) < 4 else b'valid')
                return SimpleNamespace(returncode={1: 28, 2: 22, 3: 0}.get(len(calls), 0))

            with patch.object(installer, 'run', fake):
                path = installer.fetch(asset, directory, False, [])
                self.assertEqual(path.read_bytes(), b'valid')
                self.assertEqual(len(calls), 4)
            with patch.object(installer, 'run', side_effect=AssertionError('network')):
                installer.fetch(asset, directory, True, [])
                path.write_bytes(b'corrupt')
                with self.assertRaisesRegex(RuntimeError, '离线补齐'):
                    installer.fetch(asset, directory, True, [])
            self.assertFalse(list(directory.glob('.download-*')))

    def test_both_architectures(self):
        manifest = json.loads((ROOT / 'assets.json').read_text())
        for arch in ('amd64', 'arm64'):
            assets = [a for a in manifest['assets'] if a.get('arch', arch) == arch]
            self.assertEqual(len(assets), 2)
            self.assertIn(arch, assets[0]['name'])
            self.assertEqual(assets[1]['name'], 'geoip.metadb')

    def test_missing_dependency(self):
        with patch.object(installer.shutil, 'which', return_value=None):
            with self.assertRaisesRegex(RuntimeError, 'apt install'):
                installer.dependencies(False, True)


class HealthProxyTests(unittest.TestCase):
    def test_health_check_bypasses_proxy(self):
        with patch.dict(os.environ, http_proxy='http://127.0.0.1:1', all_proxy='socks5://127.0.0.1:1'), patch.object(installer, 'active', return_value=True), patch.object(installer, 'run', return_value=SimpleNamespace(returncode=0, stdout=b'{"version":"test"}')) as run:
            self.assertTrue(installer.healthy())
        args = run.call_args.args
        self.assertEqual(args[args.index('--noproxy') + 1], '*')


class Transactions(unittest.TestCase):
    def exercise(self, running=False, fail=False, upgrade=True):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config, binary = root / 'etc', root / 'bin'
            config.mkdir(); binary.mkdir()
            unit = root / 'mihomo.service'
            project = root / 'project'; project.mkdir()
            for name in installer.PROJECT:
                (project / name).write_text('new ' + name)
                destination = binary / name if name == 'mnode' else config / name
                destination.write_text('old ' + name)
            (binary / 'mihomo').write_bytes(b'old kernel')
            (config / 'config.yaml').write_text('user config')
            (config / 'sub.b64').write_text('user subscription')
            (config / 'geoip.metadb').write_bytes(b'old db')
            archive = root / 'kernel.gz'
            with gzip.open(archive, 'wb') as target:
                target.write(b'new kernel')
            db = root / 'db'; db.write_bytes(b'new db')
            calls = []

            def fake(*args, **kwargs):
                calls.append(tuple(str(a) for a in args))
                return SimpleNamespace(returncode=0)

            opts = SimpleNamespace(upgrade=upgrade, subscription=None)
            with contextlib.ExitStack() as stack:
                for name, value in [('CONFIG', config), ('BIN', binary), ('UNIT', unit), ('HERE', project)]:
                    stack.enter_context(patch.object(installer, name, value))
                stack.enter_context(patch.object(installer, 'compatible_service', return_value=True))
                stack.enter_context(patch.object(installer, 'active', return_value=running))
                stack.enter_context(patch.object(installer, 'healthy', return_value=not fail))
                stack.enter_context(patch.object(installer, 'run', fake))
                if fail:
                    with self.assertRaisesRegex(RuntimeError, '健康检查失败'):
                        installer.install(opts, [archive, db], {})
                else:
                    installer.install(opts, [archive, db], {})
            expected = b'new kernel' if upgrade and not fail else b'old kernel'
            self.assertEqual((binary / 'mihomo').read_bytes(), expected)
            self.assertEqual((config / 'config.yaml').read_text(), 'user config')
            self.assertEqual((config / 'sub.b64').read_text(), 'user subscription')
            self.assertEqual(('systemctl', 'restart', 'mihomo') in calls, running and upgrade)
            self.assertEqual(calls[0][:3], ('unshare', '--net', '--'))
            self.assertFalse(list(config.glob('.install-*')))

    def test_stopped_upgrade(self): self.exercise()
    def test_running_upgrade(self): self.exercise(running=True)
    def test_restart_rollback(self): self.exercise(running=True, fail=True)
    def test_repeat_install_preserves(self): self.exercise(upgrade=False)


class FreshInstall(unittest.TestCase):
    def test_fresh_and_validation_failure(self):
        for fail in (False, True):
            with tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                config, binary, unit = root / 'config', root / 'bin', root / 'mihomo.service'
                archive, db, sub = root / 'kernel.gz', root / 'db', root / 'sub'
                with gzip.open(archive, 'wb') as stream:
                    stream.write(b'fake kernel')
                db.write_bytes(b'fake db'); sub.write_text('synthetic subscription')
                calls = []

                def run(*args, **kwargs):
                    calls.append(tuple(str(a) for a in args))
                    if '--output' in args:
                        Path(args[args.index('--output') + 1]).write_text('mixed-port: 7890')
                    if args[0] == 'unshare' and fail:
                        raise subprocess.CalledProcessError(1, args)
                    return SimpleNamespace(returncode=0)

                with contextlib.ExitStack() as stack:
                    for name, value in [('CONFIG', config), ('BIN', binary), ('UNIT', unit)]:
                        stack.enter_context(patch.object(installer, name, value))
                    stack.enter_context(patch.object(installer, 'run', run))
                    stack.enter_context(patch.object(installer, 'compatible_service', return_value=False))
                    stack.enter_context(patch.object(installer, 'active', return_value=False))
                    opts = SimpleNamespace(upgrade=False, subscription=sub)
                    if fail:
                        with self.assertRaises(subprocess.CalledProcessError):
                            installer.install(opts, [archive, db], {})
                        self.assertFalse((config / 'config.yaml').exists())
                        self.assertFalse((binary / 'mihomo').exists())
                    else:
                        installer.install(opts, [archive, db], {})
                        self.assertEqual((config / 'sub.b64').read_bytes(), sub.read_bytes())
                        self.assertEqual((config / 'sub.b64').stat().st_mode & 0o777, 0o600)
                        self.assertEqual((config / 'mnode-tui.py').stat().st_mode & 0o777, 0o644)
                        self.assertIn('ExecStart=', unit.read_text())
                    self.assertFalse(any(c[:2] in [('systemctl', 'start'), ('systemctl', 'enable')] for c in calls))

    def test_service_incompatible(self):
        with patch.object(installer, 'run', side_effect=[SimpleNamespace(stdout='loaded'), SimpleNamespace(stdout='argv[]=/opt/mihomo')]):
            with self.assertRaisesRegex(RuntimeError, '不兼容'):
                installer.compatible_service()

    def test_shared_lock(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / '.mnode.lock'
            with path.open('a') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                result = subprocess.run(['flock', '-n', str(path), 'true'])
                self.assertNotEqual(result.returncode, 0)
            self.assertEqual(subprocess.run(['flock', '-n', str(path), 'true']).returncode, 0)


class CLI(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = dict(os.environ, PATH=str(self.root) + ':' + os.environ['PATH'],
                        MIHOMO_CONFIG_DIR=str(self.root), MIHOMO_GROUP='组 /?"',
                        TRACE=str(self.root / 'trace'))
        self.command = self.root / 'mnode'
        self.command.write_text((ROOT / 'mnode').read_text().replace('if [ "$EUID" -ne 0 ]; then', 'if false; then'))
        self.command.chmod(0o755)
        self.script('curl', '''#!/usr/bin/env python3
import sys,os,json
args=sys.argv[1:]
with open(os.environ['TRACE'],'a') as f: f.write(json.dumps(args)+'\\n')
if os.environ.get('FAIL_API'): sys.exit(22)
if '-X' in args: print('204'); sys.exit()
if any('/version' in x for x in args): print('{"version":"test"}')
elif any('/group/' in x for x in args): print('{"slow":42,"fast":1}')
elif any(x.endswith('/proxies') for x in args): print(json.dumps({'proxies':{'组 /?"':{'type':'Selector','now':'123'}}}))
else: print(json.dumps({'now':'123','all':['123','中文 " /?&','AUTO']}))
''')
        self.script('systemctl', '#!/bin/sh\nexit 1\n')
        self.script('sudo', '#!/bin/sh\n[ -z "$CANCEL_SUDO" ] || exit 1\ncase "$1" in --preserve-env=*) shift; shift;; esac\nexec "$@"\n')

    def script(self, name, content):
        path = self.root / name; path.write_text(content); path.chmod(0o755)

    def cli(self, *args, **kwargs):
        return subprocess.run([str(self.command), *args], env=self.env,
                              text=True, capture_output=True, timeout=10, **kwargs)

    def test_json_special_names(self):
        self.assertIn('组 /?"', json.loads(self.cli('groups', '--json').stdout))
        self.assertEqual(len(json.loads(self.cli('list', '--json').stdout)['all']), 3)
        for name in ('123', '中文 " /?&'):
            self.assertEqual(self.cli('use', '--name', name).returncode, 0)
            args = json.loads((self.root / 'trace').read_text().splitlines()[-1])
            self.assertEqual(json.loads(args[args.index('-d') + 1])['name'], name)
            self.assertTrue(any('%2F%3F%22' in arg for arg in args))
        self.assertEqual(self.cli('use', '002').returncode, 0)
        self.assertNotEqual(self.cli('use', '0').returncode, 0)

    def test_control_api_bypasses_proxy_environment(self):
        self.env.update(http_proxy='http://127.0.0.1:1', https_proxy='http://127.0.0.1:1',
                        all_proxy='socks5://127.0.0.1:1', NO_PROXY='')
        for args in [('groups', '--json'), ('use', '--name', 'AUTO'), ('test',)]:
            self.assertEqual(self.cli(*args).returncode, 0)
        calls = [json.loads(line) for line in (self.root / 'trace').read_text().splitlines()]
        self.assertTrue(calls)
        for args in calls:
            self.assertIn('--noproxy', args)
            self.assertEqual(args[args.index('--noproxy') + 1], '*')

    def test_failures_and_non_tty(self):
        self.env['FAIL_API'] = '1'
        for args in [('test',), ('ip',), ('list',), ('on',)]:
            self.assertNotEqual(self.cli(*args).returncode, 0)
        self.assertNotEqual(self.cli('tui', input='0\n').returncode, 0)

    def test_ssh_guard_and_cancel(self):
        self.env['SSH_CONNECTION'] = 'test'
        result = self.cli('mode', 'tun')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('SSH', result.stdout)
        self.command = ROOT / 'mnode'
        self.env['CANCEL_SUDO'] = '1'
        self.assertNotEqual(self.cli('update').returncode, 0)
        self.assertFalse((self.root / '.mnode.lock').exists())

    def test_update_failure_cleanup(self):
        (self.root / 'build-config.py').write_text('raise SystemExit(1)\n')
        (self.root / 'config.yaml').write_text('mixed-port: 7890\n')
        (self.root / 'sub.b64').write_text('old')
        result = self.cli('update', input='synthetic\n')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(list(self.root.glob('.mnode-sub.*')))
        self.assertFalse(list(self.root.glob('.mnode-staging.*')))
        self.assertEqual((self.root / 'sub.b64').read_text(), 'old')

    def test_configuration_commit_and_restart_rollback(self):
        for restart_fails in (False, True):
            (self.root / 'build-config.py').write_bytes((ROOT / 'build-config.py').read_bytes())
            old_config = 'mixed-port: 7890\n'
            old_sub = 'old subscription'
            (self.root / 'config.yaml').write_text(old_config)
            (self.root / 'sub.b64').write_text(old_sub)
            self.script('mihomo', '#!/bin/sh\nexit 0\n')
            self.env['MIHOMO_BIN'] = str(self.root / 'mihomo')
            self.script('systemctl', '#!/bin/sh\n' + ('[ "$1" != restart ]\n' if restart_fails else 'exit 0\n'))
            line = 'ss://' + base64.b64encode(b'aes-128-gcm:test').decode() + '@127.0.0.1:12345#new'
            result = self.cli('update', input=line)
            if restart_fails:
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual((self.root / 'config.yaml').read_text(), old_config)
                self.assertEqual((self.root / 'sub.b64').read_text(), old_sub)
            else:
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('geodata-mode: false', (self.root / 'config.yaml').read_text())
                self.assertEqual((self.root / 'sub.b64').read_text(), line)
                self.assertEqual((self.root / 'config.yaml').stat().st_mode & 0o777, 0o600)
            self.assertFalse(list(self.root.glob('.mnode-sub.*')))

    def test_candidate_validation_rejected(self):
        (self.root / 'build-config.py').write_bytes((ROOT / 'build-config.py').read_bytes())
        (self.root / 'config.yaml').write_text('mixed-port: 7890\n')
        (self.root / 'sub.b64').write_text('old')
        self.script('mihomo', '#!/bin/sh\nexit 1\n')
        self.env['MIHOMO_BIN'] = str(self.root / 'mihomo')
        line = 'ss://' + base64.b64encode(b'aes-128-gcm:test').decode() + '@127.0.0.1:12345#new'
        self.assertNotEqual(self.cli('update', input=line).returncode, 0)
        self.assertEqual((self.root / 'sub.b64').read_text(), 'old')
        self.assertFalse((self.root / 'config.yaml.bak').exists())


class MenuTests(unittest.TestCase):
    def test_paging_filter_name(self):
        menu = tui.Menu(str(ROOT / 'mnode'))
        names = [f'node{i}' for i in range(30)] + ['123']
        calls = []

        def run(*args, **kwargs):
            calls.append(args)
            return {'all': names, 'now': 'node0'} if kwargs.get('capture') else 0

        with patch.object(menu, 'run', run), patch('builtins.input', side_effect=['n', 'p', 'f', '123', '1', 's', '123', 'invalid', '0']):
            menu.nodes()
        self.assertEqual(calls[1], ('use', '--name', '123', '-g', menu.group))

    def test_ssh_default_cancel(self):
        menu = tui.Menu(str(ROOT / 'mnode'))
        with patch.dict(os.environ, SSH_CONNECTION='test'), patch.object(menu, 'run') as run, patch('builtins.input', side_effect=['8', '2', '', '0']):
            menu.loop()
            run.assert_called_once_with('mode')

    def test_all_actions_and_group_selection(self):
        menu = tui.Menu(str(ROOT / 'mnode'))
        with patch.object(menu, 'run', return_value=0) as run, patch('builtins.input', side_effect=['bad', '1', '2', '3', '6', '7', '9', '11', '8', '1', '0']):
            menu.loop()
            for expected in [('status',), ('on',), ('off',), ('use', '--name', 'AUTO', '-g', menu.group), ('test', menu.group), ('ip',), ('help',), ('mode', 'mixed')]:
                self.assertIn(expected, [call.args for call in run.call_args_list])
        with patch.object(menu, 'run', return_value={'新组': {'type': 'Selector'}}), patch('builtins.input', return_value='1'):
            menu.groups()
            self.assertEqual(menu.group, '新组')

    def test_paste_and_file_updates(self):
        menu = tui.Menu(str(ROOT / 'mnode'))
        streams = []

        def run(*args, **kwargs):
            stream = kwargs['stdin']
            self.assertEqual(stream.read(), 'synthetic\n')
            self.assertEqual(os.fstat(stream.fileno()).st_mode & 0o777, 0o600)
            streams.append(stream)
            return 1

        with patch.object(menu, 'run', run), patch('builtins.input', side_effect=['2', 'synthetic', '.']):
            menu.subscription()
        self.assertTrue(streams[0].closed)
        with patch.object(menu, 'run') as run, patch('builtins.input', side_effect=['2', '.']):
            menu.subscription()
            run.assert_not_called()

    def test_proxy_environment_prints_command_and_exits(self):
        for choice, command in [('1', 'export https_proxy=http://127.0.0.1:7890 http_proxy=http://127.0.0.1:7890 all_proxy=socks5://127.0.0.1:7890'),
                                ('2', 'unset https_proxy http_proxy all_proxy')]:
            menu = tui.Menu(str(ROOT / 'mnode'))
            output = io.StringIO()
            before = dict(os.environ)
            with contextlib.redirect_stdout(output), patch('builtins.input', side_effect=['12', choice]) as prompt, patch.object(menu, 'run') as run:
                menu.loop()
            self.assertEqual(prompt.call_count, 2)
            run.assert_not_called()
            self.assertEqual(dict(os.environ), before)
            self.assertIn(command, output.getvalue())
            self.assertIn('本次 Shell 会话', output.getvalue())
            self.assertIn('菜单未执行', output.getvalue())

    def test_proxy_environment_cancel_returns_to_menu(self):
        menu = tui.Menu(str(ROOT / 'mnode'))
        with patch('builtins.input', side_effect=['12', '0', '0']) as prompt:
            menu.loop()
        self.assertEqual(prompt.call_count, 3)

    def test_eof(self):
        with patch.object(tui.sys.stdin, 'isatty', return_value=True), patch.object(tui.sys.stdout, 'isatty', return_value=True), patch.object(tui.sys, 'argv', ['menu', str(ROOT / 'mnode')]), patch('builtins.input', side_effect=EOFError):
            self.assertEqual(tui.main(), 0)


class Converter(unittest.TestCase):
    def test_plain_base64_and_modes(self):
        line = 'ss://' + base64.b64encode(b'aes-128-gcm:test').decode() + '@127.0.0.1:12345/?plugin=simple-obfs%3Bobfs%3Dhttp#same'
        with tempfile.TemporaryDirectory() as temp:
            source, output = Path(temp) / 'sub', Path(temp) / 'config'
            for mode in ('mixed', 'tun'):
                for encoded in (False, True):
                    raw = line + '\n' + line
                    source.write_text(base64.b64encode(raw.encode()).decode() if encoded else raw)
                    subprocess.run(['python3', str(ROOT / 'build-config.py'), '--subscription', str(source), '--output', str(output), '--mode', mode], check=True, stdout=subprocess.DEVNULL)
                    config = output.read_text()
                    self.assertIn('same #2', config)
                    self.assertIn('plugin: obfs', config)
                    self.assertIn('geo-auto-update: false', config)
                    self.assertEqual('auto-route: true' in config, mode == 'tun')
                    self.assertEqual(output.stat().st_mode & 0o777, 0o600)


if __name__ == '__main__':
    unittest.main()
