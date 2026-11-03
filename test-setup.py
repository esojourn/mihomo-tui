import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock
import io
import socket
import ssl
import urllib.error

spec = importlib.util.spec_from_file_location("wizard", Path(__file__).resolve().parent / "setup-wizard.py")
wizard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wizard)

ROOT = Path(__file__).resolve().parent

class SubscriptionTests(unittest.TestCase):
    def convert(self, text):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / 'sub'
            target = Path(temp) / 'config'
            source.write_text(text)
            result = subprocess.run([sys.executable, str(ROOT / 'build-config.py'), '--subscription', str(source), '--output', str(target)], capture_output=True)
            return result.returncode, target.read_text() if target.exists() else ''

    def test_yaml_isolation(self):
        code, content = self.convert('tun: {enable: true}\nexternal-controller: 0.0.0.0:9090\nproxies:\n - {name: demo, type: trojan, server: example.invalid, port: 443, password: synthetic}\n')
        self.assertEqual(code, 0)
        self.assertIn('127.0.0.1:9090', content)
        self.assertNotIn('enable: true', content)
        self.assertIn('trojan', content)

    def test_provider_only_rejected(self):
        self.assertNotEqual(self.convert('proxy-providers: {remote: {type: http}}')[0], 0)

    def test_unsafe_yaml_rejected(self):
        self.assertNotEqual(self.convert('!!python/object/apply:os.system ["false"]')[0], 0)

class FetchTests(unittest.TestCase):
    def test_clash_headers(self):
        response = io.BytesIO(b'ss://synthetic')
        response.headers = {'Content-Type': 'text/plain'}
        with patch.object(wizard, 'ask', return_value='https://example.invalid/?token=private'), patch.object(wizard.urllib.request, 'build_opener') as factory:
            factory.return_value.open.return_value = response
            self.assertEqual(wizard.subscription('A'), b'ss://synthetic')
            request = factory.return_value.open.call_args[0][0]
            self.assertEqual(request.get_header('User-agent'), 'clash.meta')
            self.assertEqual(request.get_header('Accept-encoding'), 'identity')

    def test_error_redaction(self):
        errors = [urllib.error.HTTPError('https://secret.invalid/token', 403, 'secret', {}, None),
                  urllib.error.URLError(socket.gaierror('secret')),
                  urllib.error.URLError(ssl.SSLCertVerificationError('secret')),
                  TimeoutError('secret')]
        for exc in errors:
            message = wizard.subscription_error(exc)
            self.assertNotIn('secret', message)
        self.assertIn('DNS', wizard.subscription_error(errors[1]))
        self.assertIn('证书', wizard.subscription_error(errors[2]))
        self.assertIn('超时', wizard.subscription_error(errors[3]))

    def test_html_falls_back_to_paste(self):
        response = io.BytesIO(b'<html>login</html>')
        response.headers = {'Content-Type': 'text/html'}
        with patch.object(wizard, 'ask', side_effect=['https://example.invalid', 'B']), patch('builtins.input', side_effect=['ss://synthetic', '.']), patch.object(wizard.urllib.request, 'build_opener') as factory:
            factory.return_value.open.return_value = response
            self.assertEqual(wizard.subscription('A'), b'ss://synthetic')

class WizardFlowTests(unittest.TestCase):
    def exercise(self, answers, failure=None, incompatible=False):
        with tempfile.TemporaryDirectory() as temp:
            config = Path(temp)
            (config / 'config.yaml').write_text('existing')
            mod = Mock(CONFIG=config, BIN=config / 'bin')
            if incompatible:
                mod.compatible_service.side_effect = RuntimeError('incompatible')
            with patch.object(wizard, 'installer', return_value=mod), patch.object(wizard.sys, 'argv', ['setup-wizard.py']), patch.object(wizard.sys.stdin, 'isatty', return_value=True), patch.object(wizard.os, 'geteuid', return_value=0), patch.object(wizard, 'ask', side_effect=answers), patch.object(wizard.subprocess, 'run', side_effect=failure) as run:
                if incompatible or failure:
                    with self.assertRaises((RuntimeError, subprocess.CalledProcessError)):
                        wizard.main()
                else:
                    wizard.main()
                return run.call_args_list

    def test_existing_config_calls_backend_once(self):
        calls = self.exercise(['1', 'n', 'YES', 'n'])
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].args[0], [sys.executable, str(ROOT / 'install.py')])

    def test_cancel_does_not_install_or_open_menu(self):
        self.assertEqual(self.exercise(['1', 'n', '']), [])

    def test_backend_failure_stops_flow(self):
        calls = self.exercise(['1', 'n', 'YES'], subprocess.CalledProcessError(1, ['installer']))
        self.assertEqual(len(calls), 1)

    def test_incompatible_service_stops_before_network(self):
        self.assertEqual(self.exercise([], incompatible=True), [])

    def test_mirror_number_and_bad_resource_url(self):
        with patch.object(wizard, 'ask', side_effect=['4', 'https://cdn.jsdelivr.net/gh/project/file.metadb', '2']):
            self.assertEqual(wizard.choose_mirror(), 'https://gh-proxy.com')

if __name__ == '__main__': unittest.main()
