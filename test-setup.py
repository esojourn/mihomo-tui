import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

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

if __name__ == '__main__': unittest.main()
