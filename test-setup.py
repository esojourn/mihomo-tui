import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
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

if __name__ == '__main__': unittest.main()
