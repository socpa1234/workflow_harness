import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('cli', ROOT/'lib/harness_cli.py')
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)

class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='harness tests ')
        self.base = Path(self.tmp.name).resolve()
        self.home = self.base/'home with spaces'
        self.home.mkdir()
        self.root = self.home/'installation'
        self.bin = self.home/'bin'
        self.env = patch.dict(os.environ, {'HOME': str(self.home)}, clear=False)
        self.env.start()
        self.codex = patch.dict(os.environ, {'CODEX_HOME': str(self.home/'.codex')})
        self.codex.start()
        self.system = patch.object(cli.platform, 'system', return_value='Darwin')
        self.system.start()

    def tearDown(self):
        self.system.stop(); self.codex.stop(); self.env.stop(); self.tmp.cleanup()

    def runcli(self, command, *extra, source=True):
        args = [command, '--root', str(self.root), '--yes']
        if command in ('install','update'):
            args += ['--bin-dir', str(self.bin)]
            if source:
                args += ['--source', str(ROOT)]
        return cli.main(args + list(extra))

    def test_full_lifecycle_preserves_outside_edits_and_project_memory(self):
        instructions = self.home/'.codex/AGENTS.md'
        instructions.parent.mkdir()
        instructions.write_text('Original instructions\n')
        self.runcli('install','--tool','both')
        self.runcli('install','--tool','both')
        self.runcli('status')
        instructions.write_text(instructions.read_text() + 'New personal instructions\n')
        repo = self.base/'repo'
        subprocess.run(['git','init','-q',str(repo)],check=True)
        self.runcli('init',str(repo))
        current = repo/'.harness/memory/current.md'
        current.write_text('Keep this memory')
        self.runcli('init',str(repo))
        self.runcli('uninstall')
        self.assertEqual(instructions.read_text(), 'Original instructions\nNew personal instructions\n')
        self.assertEqual(current.read_text(),'Keep this memory')
        self.assertFalse((self.bin/'workflow-harness').exists())
        self.runcli('install','--tool','codex')

    def test_dry_run_does_not_create_installation(self):
        self.runcli('install','--tool','codex','--dry-run')
        self.assertFalse(self.root.exists())
        self.assertFalse((self.home/'.codex').exists())

    def test_unowned_file_prevents_all_changes(self):
        p=self.home/'.claude/agents/implementation-reviewer.md'
        p.parent.mkdir(parents=True); p.write_text('User agent')
        with self.assertRaises(cli.Error):self.runcli('install','--tool','both')
        self.assertFalse(self.root.exists())
        self.assertFalse((self.home/'.codex/AGENTS.md').exists())
        self.assertEqual(p.read_text(),'User agent')

    def test_edited_managed_file_blocks_uninstall(self):
        self.runcli('install','--tool','codex')
        p=self.home/'.codex/agents/plan-reviewer.toml'
        p.write_text('User changed it')
        with self.assertRaises(cli.Error):self.runcli('uninstall')
        self.assertTrue((self.root/'manifest.json').exists())
        self.assertEqual(p.read_text(),'User changed it')

    def test_update_preserves_selection_and_previous_release(self):
        self.runcli('install','--tool','both')
        source=self.base/'new source'
        import shutil
        for rel in cli.PACKAGE_FILES:
            dst=source/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/rel,dst)
        next_version = cli.VERSION + '-test'
        (source/'VERSION').write_text(next_version + '\n')
        self.runcli('update','--version',next_version,'--source',str(source),source=False)
        self.assertEqual(json.loads((self.root/'manifest.json').read_text())['selected_tools'],'both')
        self.assertTrue((self.root/'releases'/cli.VERSION).is_dir())
        self.runcli('uninstall')

    def test_known_development_link_is_restored(self):
        p=self.home/'.codex/agents/plan-reviewer.toml';p.parent.mkdir(parents=True)
        target=ROOT/'.codex/agents/plan-reviewer.toml';p.symlink_to(target)
        self.runcli('install','--tool','codex')
        self.assertFalse(p.is_symlink())
        self.runcli('uninstall')
        self.assertTrue(p.is_symlink());self.assertEqual(p.resolve(),target)

    def test_backup_symlink_conflict_leaves_no_lock(self):
        self.root.mkdir()
        outside=self.base/'outside';outside.mkdir()
        (self.root/'backups').symlink_to(outside)
        with self.assertRaises(cli.Error):cli.transaction(self.root,[])
        self.assertFalse((self.root/'.lock').exists())
        self.assertEqual(list(outside.iterdir()),[])

    def test_transaction_rolls_back_after_partial_failure(self):
        a=self.home/'a';b=self.home/'b';a.write_text('before')
        before=cli.snap(a)
        changes=[(a,before,cli.file_snap(b'after')),(b,cli.snap(b),cli.file_snap(b'new'))]
        original=cli.put
        def fail(path,value):
            if path==b:raise OSError('simulated disk failure')
            original(path,value)
        with patch.object(cli,'put',side_effect=fail):
            with self.assertRaises(OSError):cli.transaction(self.root,changes)
        self.assertEqual(a.read_text(),'before');self.assertFalse(b.exists())

    def test_archive_path_and_symlink_rejected(self):
        archive=self.base/'bad.tar.gz';dst=self.base/'extract';dst.mkdir()
        for name,kind in [('../escape',tarfile.REGTYPE),('VERSION',tarfile.SYMTYPE)]:
            with tarfile.open(archive,'w:gz') as tar:
                info=tarfile.TarInfo(name);info.type=kind;info.size=0;tar.addfile(info,io.BytesIO())
            with self.assertRaises(cli.Error):cli.unpack(archive,dst)
        self.assertFalse((self.base/'escape').exists())

    def test_checksum_failure_changes_nothing(self):
        archive=self.base/'asset';archive.write_bytes(b'invalid')
        sums=self.base/'SHA256SUMS';sums.write_text('0'*64+'  workflow-harness-v0.1.0.tar.gz\n')
        with self.assertRaises(cli.Error):
            self.runcli('install','--tool','codex','--version','v0.1.0','--archive',str(archive),'--checksums',str(sums),source=False)
        self.assertFalse(self.root.exists())

    def test_init_linked_worktree_and_tracked_conflict(self):
        repo=self.base/'repo';subprocess.run(['git','init','-q',str(repo)],check=True)
        subprocess.run(['git','-C',str(repo),'-c','user.name=Test','-c','user.email=test@example.com','commit','--allow-empty','-qm','init'],check=True)
        worktree=self.base/'worktree'
        subprocess.run(['git','-C',str(repo),'worktree','add','-qb','other',str(worktree)],check=True)
        self.runcli('init',str(worktree))
        p=repo/'.harness/plans/tracked.md';p.parent.mkdir(parents=True);p.write_text('tracked')
        subprocess.run(['git','-C',str(repo),'add','-f',str(p)],check=True)
        with self.assertRaises(cli.Error):self.runcli('init',str(repo))
        self.assertEqual(p.read_text(),'tracked')

    def test_update_inherits_custom_bin_directory(self):
        self.runcli('install','--tool','codex')
        cli.main(['install','--root',str(self.root),'--tool','codex','--source',str(ROOT),'--yes'])
        self.assertTrue((self.bin/'workflow-harness').exists())

    def test_changed_codex_home_cannot_orphan_managed_files(self):
        self.runcli('install','--tool','codex')
        with patch.dict(os.environ,{'CODEX_HOME':str(self.home/'other codex')}):
            with self.assertRaises(cli.Error):
                self.runcli('install','--tool','codex')
        self.assertFalse((self.home/'other codex').exists())
        self.runcli('uninstall')
        self.assertFalse((self.home/'.codex/AGENTS.md').exists())

    def test_init_unignore_rule_creates_no_private_files(self):
        repo=self.base/'repo';subprocess.run(['git','init','-q',str(repo)],check=True)
        (repo/'.gitignore').write_text('!/.harness/\n!/.harness/**\n')
        exclude=repo/'.git/info/exclude';before=exclude.read_bytes()
        with self.assertRaises(cli.Error):self.runcli('init',str(repo))
        self.assertFalse((repo/'.harness').exists())
        self.assertEqual(exclude.read_bytes(),before)

    def test_packaged_bootstrap_and_installed_launcher(self):
        import shutil
        spec=importlib.util.spec_from_file_location('packager',ROOT/'scripts/package.py')
        packager=importlib.util.module_from_spec(spec);spec.loader.exec_module(packager)
        out=self.base/'distribution';asset=packager.build(out,allow_dirty=True)
        with tarfile.open(asset) as tar:
            names=tar.getnames()
            self.assertEqual(set(names),set(cli.PACKAGE_FILES+['RELEASE.json']))
            self.assertFalse(any('.harness' in name for name in names))
        # Exercise the downloaded standalone shell installer using a curl transport fixture.
        bootstrap=self.base/'downloaded-install.sh';shutil.copy2(ROOT/'install.sh',bootstrap)
        transport=self.base/'transport';transport.mkdir()
        curl=transport/'curl'
        curl.write_text('#!/usr/bin/env python3\nimport os,sys,shutil\nfrom pathlib import Path\na=sys.argv[1:]\nurl=next(x for x in a if x.startswith("https://"))\nshutil.copyfile(Path(os.environ["FIXTURE_ASSETS"])/url.rsplit("/",1)[1],a[a.index("-o")+1])\n')
        curl.chmod(0o755)
        env=dict(os.environ,PATH=str(transport)+os.pathsep+os.environ['PATH'],FIXTURE_ASSETS=str(out))
        result=subprocess.run(['sh',str(bootstrap),'--version',cli.VERSION,'--tool','both','--root',str(self.root),'--bin-dir',str(self.bin),'--yes'],env=env,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        installed=self.bin/'workflow-harness'
        result=subprocess.run([str(installed),'status','--root',str(self.root)],env=env,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('OK',result.stdout)
        self.runcli('uninstall')

if __name__=='__main__':unittest.main()
