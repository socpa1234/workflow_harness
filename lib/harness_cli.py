#!/usr/bin/env python3
"""Personal workflow installer. Python 3.9+, standard library only."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request

REPO = 'socpa1234/workflow_harness'
VERSION = 'v0.1.1'
BEGIN = '<!-- workflow-harness:begin -->'
END = '<!-- workflow-harness:end -->'
PACKAGE_FILES = ['VERSION', 'README.md', 'install.sh', 'bin/workflow-harness',
                 'lib/harness_cli.py', 'rules/AGENTS.md',
                 'rules/governance/planning.md', 'rules/governance/memory-writing.md',
                 'agents/plan-reviewer.md', 'agents/implementation-reviewer.md',
                 'adapters/codex/README.md', 'adapters/claude/README.md', '.codex/agents/plan-reviewer.toml',
                 'docs/installation.md']

class Error(Exception):
    pass


def digest(data):
    return hashlib.sha256(data).hexdigest()


def snap(path):
    if path.is_symlink():
        return {'kind': 'link', 'target': os.readlink(path)}
    if path.is_file():
        return {'kind': 'file', 'data': base64.b64encode(path.read_bytes()).decode(),
                'mode': path.stat().st_mode & 0o777}
    if path.exists():
        raise Error('Not a regular file: ' + str(path))
    return {'kind': 'missing'}


def file_snap(data, mode=0o644):
    return {'kind': 'file', 'data': base64.b64encode(data).decode(), 'mode': mode}


def content(snapshot):
    return base64.b64decode(snapshot['data'])


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    if value['kind'] == 'missing':
        if path.exists() or path.is_symlink():
            path.unlink()
        return
    tmp = path.parent / ('.' + path.name + '.harness-' + str(os.getpid()))
    try:
        if value['kind'] == 'link':
            tmp.symlink_to(value['target'])
        else:
            tmp.write_bytes(content(value))
            tmp.chmod(value['mode'])
        os.replace(tmp, path)
    finally:
        if tmp.exists() or tmp.is_symlink():
            tmp.unlink()


def safe_parent(path):
    # Do not redirect installation through a symlinked ancestor.
    for parent in path.parents:
        if parent.is_symlink():
            raise Error('Symlinked parent requires manual setup: ' + str(parent))


def load_manifest(root):
    p = root / 'manifest.json'
    if not p.exists():
        return None
    data = json.loads(p.read_text())
    if data.get('schema_version') != 1 or data.get('install_root') != str(root):
        raise Error('Unsupported or misplaced manifest')
    return data


def block(root):
    return ('\n' + BEGIN + '\n'
            'Read and follow the personal workflow rules at: ' + str(root / 'current/rules/AGENTS.md') + '\n'
            'Harness root: ' + str(root / 'current') + '\n'
            'Before plan review, use plan_reviewer with original requirements and all project plans.\n'
            'Follow the workflow routing rules: formal work requires implementation_reviewer after checks; lightweight work uses conditional review. Use a CODE/RUN/ENV request when reviewing.\n'
            'Project plans and shared memory live at the Git repository root under .harness/.\n'
            + END + '\n')


def registrations(root, tool):
    home = Path.home()
    codex = Path(os.environ.get('CODEX_HOME', str(home / '.codex'))).expanduser().absolute()
    claude = home / '.claude'
    out = []
    for name in ['plan', 'implementation']:
        role = name + '-reviewer'
        instruction = ('Harness root: ' + str(root / 'current') + '. '
                       'Read rules/AGENTS.md and agents/' + role + '.md from that root and follow them. '
                       'For plan review also read rules/governance/planning.md. '
                       'Read original inputs; do not modify source, plans or shared memory. '
                       'Return findings to the parent. Do not spawn another reviewer. '
                       'For RUN/ENV, if execution permissions are insufficient, request original execution logs '
                       'from the parent and report unverified scope. Never claim an unrun test passed.')
        if tool == 'codex':
            text = ('name = ' + json.dumps(name + '_reviewer') + '\n'
                    'description = ' + json.dumps('Independent ' + name + ' review; follow the workflow role.') + '\n'
                    'sandbox_mode = "read-only"\n'
                    'developer_instructions = ' + json.dumps(instruction, ensure_ascii=False) + '\n')
            out.append((codex / 'agents' / (role + '.toml'), text))
        else:
            text = ('---\nname: ' + role + '\ndescription: Independent ' + name + ' review following personal workflow rules.\n'
                    'tools: Read, Grep, Glob\nmodel: inherit\n---\n\n' + instruction + '\n')
            out.append((claude / 'agents' / (role + '.md'), text))
    out.append(((codex / 'AGENTS.md') if tool == 'codex' else claude / 'CLAUDE.md', None))
    return out


def managed_check(entry):
    path = Path(entry['path'])
    actual = snap(path)
    if entry['kind'] == 'block':
        if actual['kind'] != 'file':
            raise Error('Managed instructions missing or replaced: ' + str(path))
        text = content(actual).decode()
        if text.count(BEGIN) != 1 or text.count(END) != 1 or text.count(entry['block']) != 1:
            raise Error('Managed block edited: ' + str(path))
    elif actual != entry['installed']:
        raise Error('Managed file edited or missing: ' + str(path))
    return actual


def inventory(source):
    return {str(p.relative_to(source)): digest(p.read_bytes()) for p in sorted(source.rglob('*')) if p.is_file()}


def verify_existing(root, manifest):
    for e in manifest['entries']:
        managed_check(e)
    release = root / 'releases' / manifest['version']
    if release.is_symlink() or not release.is_dir() or inventory(release) != manifest['inventory']:
        raise Error('Installed release changed; restore it before update/uninstall')


def validate_source(source, version):
    if not re.fullmatch(r'v\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?', version):
        raise Error('Use a version such as v0.1.0')
    for rel in PACKAGE_FILES:
        p = source / rel
        if p.is_symlink() or not p.is_file():
            raise Error('Missing or symlinked package file: ' + rel)
    if (source / 'VERSION').read_text().strip() != version:
        raise Error('Package VERSION does not match requested version')


def preview(changes, args):
    for path, before, after in changes:
        action = 'remove' if after['kind'] == 'missing' else 'write'
        print(action + ': ' + str(path))
        if before['kind'] == 'link':
            print('  existing link: ' + before['target'])
    if args.dry_run:
        print('Dry run: no installation changes made.')
        return False
    if not args.yes:
        if not sys.stdin.isatty():
            raise Error('Non-interactive changes require --yes (or --dry-run)')
        if input('Apply these changes? [y/N] ').lower() != 'y':
            return False
    return True


def transaction(root, changes, stage=None, release=None):
    root.mkdir(parents=True, exist_ok=True)
    journal = root / 'backups' / (str(time.time_ns()))
    safe_parent(journal)
    lock = root / '.lock'
    try:
        lock.mkdir()
    except FileExistsError:
        raise Error('Another transaction or interrupted run exists: ' + str(lock))
    done = []
    moved = False
    try:
        journal.mkdir(parents=True, mode=0o700)
        (journal / 'changes.json').write_text(json.dumps([
            {'path': str(p), 'before': b, 'after': a} for p, b, a in changes], indent=2))
        (journal / 'changes.json').chmod(0o600)
        if stage is not None:
            if release.exists() or release.is_symlink():
                raise Error('Release appeared during installation')
            release.parent.mkdir(parents=True, exist_ok=True)
            moved = True
            shutil.copytree(stage, release)
        for p, before, after in changes:
            if snap(p) != before:
                raise Error('File changed during installation: ' + str(p))
            put(p, after)
            done.append((p, before, after))
        print('Applied. Backup: ' + str(journal))
    except BaseException:
        failed = []
        for p, before, after in reversed(done):
            try:
                if snap(p) != after:
                    raise Error('External edit')
                put(p, before)
            except Exception:
                failed.append(str(p))
        if moved and not failed:
            shutil.rmtree(release)
        if failed:
            print('Recovery required; preserved backup at ' + str(journal) + ': ' + ', '.join(failed), file=sys.stderr)
        raise
    finally:
        lock.rmdir()


def install(args, source):
    root = args.root
    version = args.version or VERSION
    validate_source(source, version)
    old = load_manifest(root)
    if args.command == 'update' and old is None:
        raise Error('Not installed')
    tool = args.tool or (old['selected_tools'] if old else None)
    if not tool and sys.stdin.isatty():
        tool = input('Tool [codex/claude/both]: ').strip()
    if tool not in ('codex', 'claude', 'both'):
        raise Error('Specify --tool codex|claude|both')
    if old:
        verify_existing(root, old)
        if tool != old['selected_tools']:
            raise Error('Tool selection change requires uninstall then install')
        if str(args.bin_dir) != old['bin_dir']:
            raise Error('Bin directory differs from existing installation')
        expected_paths = {str(p) for t in (['codex', 'claude'] if tool == 'both' else [tool]) for p, _ in registrations(root, t)}
        expected_paths.update([str(args.bin_dir / 'workflow-harness'), str(root / 'current')])
        if expected_paths != {e['path'] for e in old['entries']}:
            raise Error('Tool configuration paths changed (for example CODEX_HOME); restore original paths before update')
        if old['version'] == version:
            expected = {rel: digest((source / rel).read_bytes()) for rel in PACKAGE_FILES}
            if any(old['inventory'].get(k) != v for k, v in expected.items()):
                raise Error('Same version has different contents; use a new version')
            print('Already installed: ' + version)
            return
    release = root / 'releases' / version
    safe_parent(release)
    if release.is_symlink():
        raise Error('Release directory cannot be a symlink')
    changes = []
    entries = []
    previous = {e['path']: e for e in old['entries']} if old else {}
    targets = []
    for t in (['codex', 'claude'] if tool == 'both' else [tool]):
        if t == 'codex':
            codex_home = Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex'))).expanduser().absolute()
            if (codex_home / 'AGENTS.override.md').exists():
                raise Error('AGENTS.override.md shadows personal rules; resolve it before installation')
        targets.extend(registrations(root, t))
    targets.extend([(args.bin_dir / 'workflow-harness', 'CLI'), (root / 'current', 'CURRENT')])
    if old and {str(p) for p, _ in targets} != set(previous):
        raise Error('Tool configuration paths changed (for example CODEX_HOME); restore original paths before update')
    for path, text in targets:
        safe_parent(path)
        before = snap(path)
        prior = previous.get(str(path))
        original = prior['original'] if prior else before
        entry = {'path': str(path), 'original': original}
        if text is None:
            if before['kind'] not in ('missing', 'file'):
                raise Error('Instructions must be a regular file: ' + str(path))
            existing = content(before).decode() if before['kind'] == 'file' else ''
            chunk = block(root)
            if prior:
                existing = existing.replace(prior['block'], '', 1)
            elif BEGIN in existing or END in existing:
                raise Error('Existing unowned workflow block: ' + str(path))
            after = file_snap((existing + chunk).encode(), before.get('mode', 0o644))
            entry.update(kind='block', block=chunk)
        else:
            if not prior and before['kind'] != 'missing':
                # Only migrate this repository's known development plan-reviewer link.
                dev = Path(__file__).resolve().parent.parent / '.codex/agents/plan-reviewer.toml'
                known = (path.name == 'plan-reviewer.toml' and before['kind'] == 'link'
                         and path.resolve().parts[-3:] == ('.codex', 'agents', 'plan-reviewer.toml')
                         and path.is_file() and path.read_bytes() == (source / '.codex/agents/plan-reviewer.toml').read_bytes())
                if not known:
                    raise Error('Existing unowned file (preserved): ' + str(path))
            if text in ('CLI', 'CURRENT'):
                target = root / 'current/bin/workflow-harness' if text == 'CLI' else release
                after = {'kind': 'link', 'target': str(target)}
                entry['kind'] = 'link'
            else:
                after = file_snap(text.encode())
                entry['kind'] = 'file'
        entry['installed'] = after
        entries.append(entry)
        changes.append((path, before, after))
    manifest_path = root / 'manifest.json'
    safe_parent(manifest_path)
    with tempfile.TemporaryDirectory(prefix='workflow-stage-') as tmp:
        stage = Path(tmp) / 'payload'
        stage.mkdir()
        for rel in PACKAGE_FILES:
            dst = stage / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source / rel, dst)
        if (source / 'RELEASE.json').is_file():
            shutil.copy2(source / 'RELEASE.json', stage / 'RELEASE.json')
        metadata = json.loads((stage / 'RELEASE.json').read_text()) if (stage / 'RELEASE.json').exists() else {}
        if metadata and (metadata.get('version') != version or not re.fullmatch(r'[a-f0-9]{40}', metadata.get('source_commit', ''))):
            raise Error('Release metadata does not match package')
        manifest = {'schema_version': 1, 'version': version, 'source_commit': metadata.get('source_commit', 'local-development'),
                    'selected_tools': tool, 'install_root': str(root), 'bin_dir': str(args.bin_dir),
                    'inventory': inventory(stage), 'entries': entries}
        changes.append((manifest_path, snap(manifest_path), file_snap((json.dumps(manifest, indent=2) + '\n').encode(), 0o600)))
        if release.exists() and inventory(release) != inventory(stage):
            raise Error('Preserved release differs from requested payload: ' + str(release))
        if preview(changes, args):
            transaction(root, changes, None if release.exists() else stage, release)
            print('Installed ' + version + '. Add to PATH if needed: ' + str(args.bin_dir))
            print('Restart Codex/Claude Code; verify both reviewer roles in a new session.')


def uninstall(args):
    old = load_manifest(args.root)
    if not old:
        raise Error('Not installed')
    verify_existing(args.root, old)
    changes = []
    for entry in old['entries']:
        path = Path(entry['path'])
        before = managed_check(entry)
        if entry['kind'] == 'block':
            remaining = content(before).decode().replace(entry['block'], '', 1)
            after = file_snap(remaining.encode(), before['mode'])
            if not remaining and entry['original']['kind'] == 'missing':
                after = {'kind': 'missing'}
        else:
            after = entry['original']
        changes.append((path, before, after))
    path = args.root / 'manifest.json'
    changes.append((path, snap(path), {'kind': 'missing'}))
    if preview(changes, args):
        transaction(args.root, changes)
        print('Uninstalled links and managed settings. Releases/backups and project .harness data preserved.')


def status(args):
    data = load_manifest(args.root)
    if not data:
        print('Not installed: ' + str(args.root))
        return
    print('Version: ' + data['version'] + '\nTools: ' + data['selected_tools'] + '\nRoot: ' + str(args.root))
    verify_existing(args.root, data)
    print('Managed settings and release contents: OK')


def git(repo, *parts):
    return subprocess.check_output(['git', '-C', str(repo), *parts], text=True).strip()


def init_project(args):
    repo = Path(git(args.repo, 'rev-parse', '--show-toplevel')).resolve()
    tracked = git(repo, 'ls-files', '--', '.harness')
    if tracked:
        raise Error('Tracked .harness files; resolve manually before init')
    workspace = repo / '.harness'
    expected = ['plans', 'memory', 'memory/progress', 'memory/history']
    if workspace.is_symlink() or (workspace.exists() and not workspace.is_dir()):
        raise Error('Workspace path conflict')
    for rel in expected:
        p = workspace / rel
        if p.is_symlink() or (p.exists() and not p.is_dir()):
            raise Error('Workspace subpath conflict: ' + str(p))
    current = workspace / 'memory/current.md'
    if current.is_symlink() or (current.exists() and not current.is_file()):
        raise Error('Memory path conflict')
    exclusion = Path(git(repo, 'rev-parse', '--git-path', 'info/exclude'))
    if not exclusion.is_absolute():
        exclusion = repo / exclusion
    safe_parent(exclusion)
    before = snap(exclusion)
    if before['kind'] not in ('file', 'missing'):
        raise Error('Exclude path conflict')
    data = content(before).decode() if before['kind'] == 'file' else ''
    changed = '/.harness/' not in data.splitlines()
    print('Initialize local workspace: ' + str(workspace))
    changes = [(exclusion, before, file_snap((data + ('\n' if data and not data.endswith('\n') else '') + '/.harness/\n').encode(), before.get('mode', 0o644)))] if changed else []
    if not preview(changes, args):
        return
    # Ignore first; never add shared .gitignore or stage project files.
    if changed:
        put(exclusion, changes[0][2])
    result = subprocess.run(['git', '-C', str(repo), 'check-ignore', '--no-index', '-q', '.harness/memory/current.md'])
    if result.returncode:
        if changed and snap(exclusion) == changes[0][2]:
            put(exclusion, before)
        raise Error('Repository ignore rules override local exclude; no workspace created')
    for rel in expected:
        (workspace / rel).mkdir(parents=True, exist_ok=True)
    if not current.exists():
        current.write_text('# Current context\n\nNo work recorded yet. Read the project plans before implementation.\n')
    result = subprocess.run(['git', '-C', str(repo), 'check-ignore', '-q', '.harness/memory/current.md'])
    if result.returncode:
        raise Error('Ignore verification failed; inspect local exclude')
    print('Workspace ready; existing plans and memory preserved.')


def download(url, path):
    if not url.startswith('https://'):
        raise Error('Downloads require HTTPS')
    with urllib.request.urlopen(url, timeout=45) as response:
        if not response.geturl().startswith('https://'):
            raise Error('Non-HTTPS redirect rejected')
        data = response.read(25_000_001)
        if len(data) > 25_000_000:
            raise Error('Download exceeds size limit')
        path.write_bytes(data)


def unpack(archive, target):
    allowed = set(PACKAGE_FILES + ['RELEASE.json'])
    with tarfile.open(archive, 'r:gz') as tar:
        members = tar.getmembers()
        seen = set()
        total = 0
        for member in members:
            name = member.name
            if name not in allowed or name in seen or not member.isfile() or member.size > 5_000_000:
                raise Error('Unexpected archive member: ' + name)
            if PurePosixPath(name).is_absolute() or '..' in PurePosixPath(name).parts:
                raise Error('Unsafe archive path')
            seen.add(name)
            total += member.size
        if total > 20_000_000 or seen != allowed:
            raise Error('Incomplete or oversized release archive')
        for member in members:
            p = target / member.name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(tar.extractfile(member).read())
            p.chmod(0o755 if member.name in ('bin/workflow-harness', 'install.sh') else 0o644)


def remote_source(args, tmp):
    version = args.version
    if not version or not re.fullmatch(r'v\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?', version):
        raise Error('HTTPS installation/update requires --version vX.Y.Z')
    asset = 'workflow-harness-' + version + '.tar.gz'
    archive = tmp / asset
    sums = tmp / 'SHA256SUMS'
    if args.archive:
        shutil.copyfile(args.archive, archive)
        if not args.checksums:
            raise Error('--archive requires --checksums')
        shutil.copyfile(args.checksums, sums)
    else:
        base = 'https://github.com/' + REPO + '/releases/download/' + version + '/'
        download(base + asset, archive)
        download(base + 'SHA256SUMS', sums)
    matches = [line.split() for line in sums.read_text().splitlines() if len(line.split()) == 2 and line.split()[1] == asset]
    if len(matches) != 1 or digest(archive.read_bytes()) != matches[0][0]:
        raise Error('Checksum mismatch')
    dst = tmp / 'payload'
    dst.mkdir()
    unpack(archive, dst)
    return dst


def main(argv=None):
    parser = argparse.ArgumentParser(description='Personal workflow installer (macOS, Python 3.9+)')
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('install', 'update', 'status', 'uninstall', 'init'):
        p = sub.add_parser(name)
        p.add_argument('--root', type=Path, default=Path.home() / '.local/share/workflow-harness')
        p.add_argument('--dry-run', action='store_true')
        p.add_argument('--yes', action='store_true')
        if name in ('install', 'update'):
            p.add_argument('--tool', choices=('codex', 'claude', 'both'))
            p.add_argument('--version')
            p.add_argument('--bin-dir', type=Path)
            p.add_argument('--source', type=Path, help='Install a local source tree')
            p.add_argument('--archive', type=Path, help='Install a local release archive')
            p.add_argument('--checksums', type=Path)
        if name == 'init':
            p.add_argument('repo', nargs='?', type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    args.root = args.root.expanduser().absolute()
    safe_parent(args.root)
    if args.root.is_symlink():
        raise Error('Install root cannot be a symlink')
    if hasattr(args, 'bin_dir'):
        existing = load_manifest(args.root)
        args.bin_dir = (args.bin_dir or (Path(existing['bin_dir']) if existing else Path.home() / '.local/bin')).expanduser().absolute()
    if args.command in ('install', 'update'):
        if platform.system() != 'Darwin':
            raise Error('Initial release supports macOS only')
        if args.command == 'update' and not args.version:
            raise Error('update requires --version')
        with tempfile.TemporaryDirectory(prefix='workflow-download-') as tmp:
            source = args.source.resolve() if args.source else remote_source(args, Path(tmp))
            install(args, source)
    elif args.command == 'status':
        status(args)
    elif args.command == 'uninstall':
        uninstall(args)
    else:
        init_project(args)

if __name__ == '__main__':
    try:
        main()
    except (Error, OSError, ValueError, subprocess.CalledProcessError, tarfile.TarError) as exc:
        print('Error: ' + str(exc), file=sys.stderr)
        sys.exit(1)
