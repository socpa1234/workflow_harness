# coding: utf-8
"""Windows behavior runs with real paths; native entry-point tests require Windows."""
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('windows_cli', ROOT/'lib/harness_cli.py')
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)
ORIGINAL_DESKTOP_PACKAGES = cli.desktop_packages


class WindowsFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='harness windows ')
        self.base = Path(self.tmp.name).resolve()
        self.home = self.base / 'home \ud55c\uae00 & (space)!'
        self.home.mkdir()
        self.root = self.home / 'installation'
        self.bin = self.root / 'bin'
        self.patches = [patch.object(cli.Path, 'home', return_value=self.home),
                        patch.object(cli.platform, 'system', return_value='Windows'),
                        patch.dict(os.environ, {'HOME': str(self.home), 'USERPROFILE': str(self.home),
                            'LOCALAPPDATA': str(self.home/'AppData/Local'), 'APPDATA': str(self.home/'AppData/Roaming'),
                            'CODEX_HOME': str(self.home/'.codex'), 'CLAUDE_CONFIG_DIR': str(self.home/'.claude'),
                            'CODEX_INSTALL_DIR': ''}),
                        patch.object(cli.shutil, 'which', return_value=None),
                        patch.object(cli, 'desktop_packages', return_value=[])]
        for p in self.patches:
            p.start()
        for tool in ('codex', 'claude'):
            executable = self.home/'.local/bin'/(tool+'.exe')
            executable.parent.mkdir(parents=True, exist_ok=True)
            executable.write_bytes(b'fixture; discovery must not execute this file')

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def runcli(self, command, *extra):
        args = [command, '--root', str(self.root), '--yes']
        if command in ('install', 'update'):
            args += ['--source', str(ROOT)]
        return cli.main(args + list(extra))

    def new_source(self):
        source = self.base/'new payload'
        for rel in cli.PACKAGE_FILES:
            target = source/rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT/rel, target)
        version = cli.VERSION + '-windows-test'
        (source/'VERSION').write_text(version+'\n', encoding='utf-8')
        return source, version


class WindowsTests(WindowsFixture):
    def test_discovery_zero_one_two_and_explicit_missing(self):
        self.assertTrue(all(cli.discover_tools().values()))
        (self.home/'.local/bin/claude.exe').unlink()
        self.runcli('install')
        self.assertEqual(cli.load_manifest(self.root)['selected_tools'], 'codex')
        self.assertFalse((self.home/'.claude').exists())
        self.runcli('uninstall')
        with self.assertRaisesRegex(cli.Error, 'Selected installation not found'):
            self.runcli('install', '--tool', 'both')
        (self.home/'.local/bin/codex.exe').unlink()
        with self.assertRaisesRegex(cli.Error, 'No supported installation'):
            self.runcli('install')
        self.assertIsNone(cli.load_manifest(self.root))

    def test_path_and_npm_discovery_and_config_is_not_installation(self):
        for p in (self.home/'.local/bin').iterdir():
            p.unlink()
        (self.home/'.codex').mkdir()
        self.assertFalse(any(cli.discover_tools().values()))
        npm = Path(os.environ['APPDATA'])/'npm/claude.cmd'
        npm.parent.mkdir(parents=True)
        npm.write_text('@exit /b 0', encoding='utf-8')
        self.assertEqual(cli.discover_tools()['claude'], npm)
        custom = self.base/'custom codex.exe'
        custom.touch()
        with patch.object(cli.shutil, 'which', side_effect=lambda name: str(custom) if name=='codex' else None):
            self.assertEqual(cli.discover_tools()['codex'], custom)

    def test_link_free_lifecycle_updates_selection_and_preserves_user_data(self):
        instructions = self.home/'.codex/AGENTS.md'
        instructions.parent.mkdir()
        instructions.write_text('Original \uaddc\uce59\n', encoding='utf-8')
        with patch.object(cli.Path, 'symlink_to', side_effect=AssertionError('Windows must not create links')):
            self.runcli('install')
            self.runcli('install')
            self.runcli('status')
            self.assertFalse((self.root/'current').exists())
            self.assertTrue((self.bin/'workflow-harness.cmd').is_file())
            installed = instructions.read_text(encoding='utf-8')
            self.assertIn(str(self.root/'releases'/cli.VERSION), installed)
            self.assertNotIn('current/rules', installed)
            instructions.write_text(installed+'Personal addition\n', encoding='utf-8')
            source, version = self.new_source()
            # Update preserves the chosen tools even if executables temporarily disappear.
            for p in (self.home/'.local/bin').iterdir():
                p.unlink()
            self.runcli('update', '--version', version, '--source', str(source))
            data = cli.load_manifest(self.root)
            self.assertEqual(data['selected_tools'], 'both')
            self.assertTrue((self.root/'releases'/cli.VERSION).is_dir())
            self.assertIn(version, instructions.read_text(encoding='utf-8'))
            self.assertIn(version, (self.bin/'workflow-harness.cmd').read_text(encoding='utf-8'))
            self.assertTrue(all('\\' not in key for key in data['inventory']))
            self.runcli('status')
            self.runcli('uninstall')
        self.assertEqual(instructions.read_text(encoding='utf-8'), 'Original \uaddc\uce59\nPersonal addition\n')
        self.assertFalse((self.bin/'workflow-harness.cmd').exists())

    def test_dry_run_and_conflicts_leave_no_installation(self):
        self.runcli('install', '--dry-run')
        self.assertFalse(self.root.exists())
        self.assertFalse((self.home/'.codex').exists())
        conflict = self.home/'.claude/agents/plan-reviewer.md'
        conflict.parent.mkdir(parents=True)
        conflict.write_text('personal', encoding='utf-8')
        with self.assertRaisesRegex(cli.Error, 'unowned'):
            self.runcli('install')
        self.assertFalse(self.root.exists())
        self.assertEqual(conflict.read_text(encoding='utf-8'), 'personal')

    def test_config_overrides_path_change_and_same_version_protection(self):
        custom = self.home/'claude custom'
        with patch.dict(os.environ, {'CLAUDE_CONFIG_DIR': str(custom)}):
            self.runcli('install')
            self.assertTrue((custom/'CLAUDE.md').exists())
            source, version = self.new_source()
            (source/'VERSION').write_text(cli.VERSION+'\n', encoding='utf-8')
            (source/'README.md').write_text('changed payload', encoding='utf-8')
            with self.assertRaisesRegex(cli.Error, 'Same version'):
                self.runcli('install', '--source', str(source))
        with self.assertRaisesRegex(cli.Error, 'configuration paths changed'):
            self.runcli('install')
        with patch.dict(os.environ, {'CLAUDE_CONFIG_DIR': str(custom)}):
            self.runcli('uninstall')
        self.assertFalse((custom/'CLAUDE.md').exists())

    def test_partial_update_failure_restores_previous_release_and_files(self):
        self.runcli('install')
        before = {p: p.read_bytes() for p in [self.root/'manifest.json', self.bin/'workflow-harness.cmd', self.home/'.codex/AGENTS.md']}
        source, version = self.new_source()
        original = cli.put
        def fail(path, value):
            if path == self.home/'.claude/agents/plan-reviewer.md' and version in cli.content(value).decode():
                raise OSError('simulated failure')
            original(path, value)
        with patch.object(cli, 'put', side_effect=fail):
            with self.assertRaises(OSError):
                self.runcli('update', '--version', version, '--source', str(source))
        for p, value in before.items():
            self.assertEqual(p.read_bytes(), value)
        self.assertFalse((self.root/'releases'/version).exists())
        self.runcli('status')

    def test_reparse_parents_and_edited_managed_files_are_preserved(self):
        with patch.object(cli, 'reparse_point', side_effect=lambda p: p == self.home):
            with self.assertRaisesRegex(cli.Error, 'Linked parent'):
                self.runcli('install')
        self.assertFalse(self.root.exists())
        self.runcli('install')
        agent = self.home/'.codex/agents/plan-reviewer.toml'
        agent.write_text('user edit', encoding='utf-8')
        with self.assertRaisesRegex(cli.Error, 'Managed file edited'):
            self.runcli('uninstall')
        self.assertEqual(agent.read_text(encoding='utf-8'), 'user edit')

    def test_windows_default_root_bin_and_snapshot_normalization(self):
        cli.main(['install', '--source', str(ROOT), '--yes'])
        root = Path(os.environ['LOCALAPPDATA'])/'workflow-harness'
        self.assertTrue((root/'bin/workflow-harness.cmd').exists())
        cli.main(['status'])
        cli.main(['uninstall', '--yes'])
        target = self.home/'snapshot'
        value = cli.file_snap(b'private', 0o600)
        cli.put(target, value)
        self.assertEqual(cli.snap(target), value)

    def test_launcher_quotes_literals_and_rejects_newlines(self):
        text = cli.windows_launcher(self.root/'releases/v1')
        self.assertIn('(space)!', text)
        self.assertIn('DisableDelayedExpansion', text)
        self.assertIn('chcp 65001', text)
        with self.assertRaises(cli.Error):
            cli.windows_launcher(Path('bad\npath'))
        with self.assertRaises(cli.Error):
            cli.windows_launcher(self.root/'%literal%')

    def test_redirected_ansi_output_is_switched_to_utf8(self):
        buffer = io.BytesIO()
        stream = io.TextIOWrapper(buffer, encoding='cp1252')
        with patch.object(sys, 'stdout', stream):
            self.runcli('status')
            stream.flush()
            self.assertEqual(stream.encoding, 'utf-8')
            self.assertIn(str(self.home), buffer.getvalue().decode('utf-8'))
        stream.detach()

    def test_windows_editor_newlines_preserve_personal_additions(self):
        self.runcli('install')
        path = self.home/'.codex/AGENTS.md'
        path.write_bytes(path.read_bytes().replace(b'\n', b'\r\n') + b'Personal addition\r\n')
        self.runcli('status')
        source, version = self.new_source()
        self.runcli('update', '--version', version, '--source', str(source))
        self.runcli('uninstall')
        self.assertEqual(path.read_bytes(), b'Personal addition\r\n')

    def test_changed_managed_text_still_blocks_update_after_newline_conversion(self):
        self.runcli('install')
        path = self.home/'.codex/AGENTS.md'
        changed = path.read_bytes().replace(b'\n', b'\r\n').replace(b'Harness root:', b'Changed root:')
        path.write_bytes(changed)
        with self.assertRaisesRegex(cli.Error, 'Managed block edited'):
            self.runcli('uninstall')
        self.assertEqual(path.read_bytes(), changed)

    def test_desktop_only_msix_and_mixed_installation(self):
        for p in (self.home/'.local/bin').iterdir():
            p.unlink()
        codex = self.home/'Apps/Codex'
        claude = self.home/'Apps/Claude'
        codex.mkdir(parents=True)
        claude.mkdir(parents=True)
        packages = [{'Name': 'OpenAI.Codex', 'InstallLocation': str(codex)},
                    {'Name': 'Claude', 'InstallLocation': str(claude)},
                    {'Name': 'Unknown', 'InstallLocation': str(self.home)}]
        with patch.object(cli, 'desktop_packages', return_value=packages):
            self.assertEqual(cli.discover_tools(), {'codex': codex, 'claude': claude})
            self.runcli('install')
            self.assertEqual(cli.load_manifest(self.root)['selected_tools'], 'both')
            self.runcli('uninstall')
            executable = self.home/'.local/bin/codex.exe'
            executable.touch()
            self.assertEqual(cli.discover_tools(), {'codex': executable, 'claude': claude})

    def test_desktop_exe_override_missing_and_standalone_codex(self):
        for p in (self.home/'.local/bin').iterdir():
            p.unlink()
        default = Path(os.environ['LOCALAPPDATA'])/'Programs/Claude/Claude.exe'
        default.parent.mkdir(parents=True)
        default.touch()
        self.assertEqual(cli.discover_tools()['claude'], default)
        explicit = self.home/'custom/Codex.exe'
        explicit.parent.mkdir()
        explicit.touch()
        self.runcli('install', '--codex-app', str(explicit))
        self.assertEqual(cli.load_manifest(self.root)['selected_tools'], 'both')
        self.runcli('uninstall')
        with self.assertRaisesRegex(cli.Error, 'existing EXE'):
            self.runcli('install', '--codex-app', str(self.home/'missing.exe'))
        with patch.dict(os.environ, {'CODEX_INSTALL_DIR': str(explicit.parent)}):
            (explicit.parent/'codex.exe').touch()
            self.assertIsNotNone(cli.discover_tools()['codex'])

    def test_desktop_query_failure_is_distinct_from_absence(self):
        # Exercise the real query function rather than the fixture's inventory stub.
        query = ORIGINAL_DESKTOP_PACKAGES
        with patch.object(cli.subprocess, 'run', side_effect=OSError('denied')):
            output = io.StringIO()
            from contextlib import redirect_stderr
            with redirect_stderr(output):
                self.assertEqual(query(), [])
            self.assertIn('detection unavailable', output.getvalue())

    def test_uninstall_rejects_changed_reparse_parent_without_deleting(self):
        self.runcli('install')
        before = {p: p.read_bytes() for p in self.home.rglob('*') if p.is_file()}
        for parent in (self.home/'.codex', self.root, self.root/'releases'/cli.VERSION):
            with patch.object(cli, 'reparse_point', side_effect=lambda p: p == parent):
                with self.assertRaises(cli.Error):
                    self.runcli('uninstall')
        self.assertEqual({p: p.read_bytes() for p in self.home.rglob('*') if p.is_file()}, before)

    @unittest.skipUnless(os.name == 'nt', 'requires native Windows cmd.exe')
    def test_native_installed_cmd_lifecycle_and_exit_codes(self):
        self.runcli('install')
        launcher = self.bin/'workflow-harness.cmd'
        env = dict(os.environ)
        env.pop('PYTHONUTF8', None)
        def run(*args):
            # No shell command interpolation: list arguments preserve spaces/metacharacters.
            return subprocess.run([str(launcher), *args, '--root', str(self.root)], env=env,
                                  capture_output=True, text=True, encoding='utf-8')
        result = run('status')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('OK', result.stdout)
        self.assertEqual(run('invalid-command').returncode, 2)
        repo = self.home/'repo \ud55c\uae00'
        subprocess.run(['git', 'init', '-q', str(repo)], check=True)
        self.assertEqual(run('init', str(repo), '--yes').returncode, 0)
        memory = repo/'.harness/memory/current.md'
        memory.write_text('keep', encoding='utf-8')
        source, version = self.new_source()
        result = run('update', '--version', version, '--source', str(source), '--yes')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(run('status').returncode, 0)
        result = run('uninstall', '--yes')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(memory.read_text(encoding='utf-8'), 'keep')

    @unittest.skipUnless(os.name == 'nt', 'requires Windows junctions')
    def test_native_junction_cannot_redirect_uninstall(self):
        self.runcli('install')
        managed = self.home/'.codex'
        outside = self.base/'external codex'
        managed.rename(outside)
        result = subprocess.run(['cmd.exe', '/d', '/c', 'mklink', '/J', str(managed), str(outside)],
                                capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        try:
            before = {p: p.read_bytes() for p in outside.rglob('*') if p.is_file()}
            with self.assertRaises(cli.Error):
                self.runcli('uninstall')
            self.assertEqual({p: p.read_bytes() for p in outside.rglob('*') if p.is_file()}, before)
        finally:
            managed.rmdir()  # Remove the junction itself, never its target.
            outside.rename(managed)

    @unittest.skipUnless(os.name == 'nt', 'requires current-user Windows MSIX inventory')
    def test_native_supported_package_query(self):
        from contextlib import redirect_stderr
        output = io.StringIO()
        with redirect_stderr(output):
            packages = ORIGINAL_DESKTOP_PACKAGES()
        self.assertEqual(output.getvalue(), '')
        self.assertIsInstance(packages, list)
        self.assertTrue(all(p.get('Name') in ('OpenAI.Codex', 'Claude') for p in packages))


if __name__ == '__main__':
    unittest.main()
