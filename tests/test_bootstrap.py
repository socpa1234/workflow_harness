# coding: utf-8
import ast
from contextlib import redirect_stderr
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
from unittest.mock import patch
import unittest
from types import SimpleNamespace
import urllib.request

from test_windows import WindowsFixture, cli, ROOT

POWERSHELL = os.environ.get('HARNESS_TEST_POWERSHELL') or shutil.which('pwsh') or shutil.which('powershell')
BOOTSTRAP = (ROOT/'install.ps1').read_text(encoding='utf-8').split("$bootstrap = @'\n", 1)[1].split("\n'@", 1)[0]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


class BootstrapTests(WindowsFixture):
    def package(self):
        packager = module('packager_fixture', ROOT/'scripts/package.py')
        out = self.base/'release assets'
        asset = packager.build(out, allow_dirty=True)
        return out, asset

    def run_bootstrap(self, out, script_root=None, *args):
        class Response(io.BytesIO):
            def geturl(self):
                return 'https://fixture.invalid/asset'
        def transport(url, timeout):
            return Response((out/url.rsplit('/',1)[1]).read_bytes())
        def install(argv):
            return cli.main(argv[4:]) or 0
        location = script_root or self.base/'download only'
        location.mkdir(exist_ok=True)
        with patch.object(sys, 'argv', ['bootstrap', str(location), '--version', cli.VERSION,
                                      '--root', str(self.root), '--yes', *args]), \
             patch('urllib.request.build_opener', return_value=SimpleNamespace(open=transport)), \
             patch('subprocess.call', side_effect=install):
            with self.assertRaises(SystemExit) as exit_result:
                exec(compile(BOOTSTRAP, str(ROOT/'install.ps1'), 'exec'), {})
        return exit_result.exception.code

    def test_package_and_bootstrap_share_legacy_archive_contract(self):
        out, asset = self.package()
        legacy = module('legacy_fixture', ROOT/'tests/fixtures/v0_1_2_cli.py')
        self.assertEqual(cli.PACKAGE_FILES, legacy.PACKAGE_FILES)
        tree = ast.parse(BOOTSTRAP)
        allowed = next(ast.literal_eval(node.value) for node in tree.body
                       if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id=='allowed' for t in node.targets))
        self.assertEqual(allowed, set(legacy.PACKAGE_FILES+['RELEASE.json']))
        extracted = self.base/'legacy unpack'
        extracted.mkdir()
        legacy.unpack(asset, extracted)
        self.assertFalse((extracted/'install.ps1').exists())
        self.assertTrue((out/'install.ps1').is_file())
        for line in (out/'SHA256SUMS').read_text(encoding='utf-8').splitlines():
            digest, name = line.split()
            self.assertEqual(cli.digest((out/name).read_bytes()), digest)
        self.assertEqual(len((out/'SHA256SUMS').read_text(encoding='utf-8').splitlines()), 3)

    def test_downloaded_python_bootstrap_installs_and_bad_checksum_preserves(self):
        out, asset = self.package()
        self.assertEqual(self.run_bootstrap(out), 0)
        self.runcli('status')
        self.runcli('uninstall')
        (out/'SHA256SUMS').write_text('0'*64+'  '+asset.name+'\n', encoding='utf-8')
        self.assertIn('Checksum mismatch', self.run_bootstrap(out))
        self.assertIsNone(cli.load_manifest(self.root))

    def test_bootstrap_rejects_unsafe_members_even_with_matching_checksum(self):
        out, asset = self.package()
        with tarfile.open(asset, 'w:gz') as archive:
            member = tarfile.TarInfo('../escape')
            member.size = 3
            archive.addfile(member, io.BytesIO(b'bad'))
        (out/'SHA256SUMS').write_text(cli.digest(asset.read_bytes())+'  '+asset.name+'\n', encoding='utf-8')
        self.assertIn('Unexpected release archive', self.run_bootstrap(out))
        self.assertFalse(self.root.exists())
        self.assertFalse((self.base/'escape').exists())

    def test_local_bootstrap_preserves_argument_boundaries(self):
        self.assertNotIn('"', BOOTSTRAP)
        self.assertEqual(self.run_bootstrap(self.base, ROOT, '--dry-run'), 0)
        self.assertFalse(self.root.exists())

    def test_each_download_redirect_requires_https(self):
        tree = ast.parse(BOOTSTRAP)
        definition = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name=='HTTPSOnlyRedirect')
        namespace = {'urllib': __import__('urllib')}
        exec(compile(ast.Module(body=[definition], type_ignores=[]), 'bootstrap redirect', 'exec'), namespace)
        req = urllib.request.Request('https://example.com/release')
        for handler in (cli.HTTPSOnlyRedirect(), namespace['HTTPSOnlyRedirect']()):
            with self.assertRaises((cli.Error, ValueError)):
                handler.redirect_request(req, None, 302, 'Found', {}, 'http://example.com/temporary')
            redirected = handler.redirect_request(req, None, 302, 'Found', {}, 'https://example.com/asset')
            self.assertEqual(redirected.full_url, 'https://example.com/asset')

    @unittest.skipIf(os.name=='nt', 'legacy install uses macOS symlinks')
    def test_real_legacy_manifest_update_to_new_version_preserves_originals(self):
        legacy = module('legacy_manifest_fixture', ROOT/'tests/fixtures/v0_1_2_cli.py')
        instruction = self.home/'.codex/AGENTS.md'
        instruction.parent.mkdir()
        instruction.write_text('personal\n', encoding='utf-8')
        old_source, _ = self.new_source()
        (old_source/'VERSION').write_text(legacy.VERSION+'\n', encoding='utf-8')
        shutil.copy2(ROOT/'tests/fixtures/v0_1_2_cli.py', old_source/'lib/harness_cli.py')
        with patch.object(cli.platform, 'system', return_value='Darwin'):
            legacy.main(['install', '--source', str(old_source), '--tool', 'both', '--root', str(self.root),
                         '--bin-dir', str(self.bin), '--yes'])
            self.runcli('update', '--source', str(ROOT), '--version', cli.VERSION)
            self.runcli('status')
            self.runcli('uninstall')
        self.assertEqual(instruction.read_text(encoding='utf-8'), 'personal\n')
        self.assertTrue((self.root/'releases'/legacy.VERSION).exists())
        self.assertTrue((self.root/'releases'/cli.VERSION).exists())

    @unittest.skipUnless(POWERSHELL, 'requires PowerShell; native CI sets HARNESS_TEST_POWERSHELL')
    def test_powershell_local_entrypoint_and_exit_status(self):
        # Python itself is selected by the script; CLI discovery is done by the child process.
        args = [POWERSHELL, '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File',
                str(ROOT/'install.ps1'), '--root', str(self.root), '--tool', 'both', '--yes']
        env = dict(os.environ, PATH=str(Path(sys.executable).parent)+os.pathsep+os.environ['PATH'])
        result = subprocess.run(args+['--dry-run'], env=env, capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Dry run', result.stdout)
        self.assertFalse(self.root.exists())
        result = subprocess.run(args, env=env, capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.root/'manifest.json').exists())
        # In child processes the actual host OS decides the platform format.
        result = subprocess.run(args+['--invalid-option'], env=env, capture_output=True, text=True, encoding='utf-8')
        self.assertNotEqual(result.returncode, 0)

    @unittest.skipUnless(POWERSHELL, 'requires PowerShell; native CI sets HARNESS_TEST_POWERSHELL')
    def test_powershell_downloaded_entrypoint_uses_verified_package(self):
        out, asset = self.package()
        downloaded = self.base/'download only'
        downloaded.mkdir()
        installer = downloaded/'install.ps1'
        shutil.copy2(ROOT/'install.ps1', installer)
        transport = self.base/'python transport'
        transport.mkdir()
        # HTTPS fixture supplied to both bootstrap and child Python without changing product code.
        (transport/'sitecustomize.py').write_text(
            'import io, os, pathlib, urllib.request, types\n'
            'class Response(io.BytesIO):\n'
            '    def geturl(self): return "https://fixture.invalid/asset"\n'
            'def fixture(url, timeout=45):\n'
            '    return Response((pathlib.Path(os.environ["FIXTURE_ASSETS"])/url.rsplit("/",1)[1]).read_bytes())\n'
            'urllib.request.build_opener = lambda *handlers: types.SimpleNamespace(open=fixture)\n', encoding='utf-8')
        env = dict(os.environ, PYTHONPATH=str(transport), FIXTURE_ASSETS=str(out),
                   PATH=str(Path(sys.executable).parent)+os.pathsep+os.environ['PATH'])
        args = [POWERSHELL, '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File',
                str(installer), '--version', cli.VERSION, '--root', str(self.root), '--tool', 'both', '--yes']
        result = subprocess.run(args, env=env, capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stderr)
        before = (self.root/'manifest.json').read_bytes()
        (out/'SHA256SUMS').write_text('0'*64+'  '+asset.name+'\n', encoding='utf-8')
        result = subprocess.run(args, env=env, capture_output=True, text=True, encoding='utf-8')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Checksum mismatch', result.stderr)
        self.assertEqual((self.root/'manifest.json').read_bytes(), before)


if __name__=='__main__':
    unittest.main()
