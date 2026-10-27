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
VERSION = 'v0.2.0'
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


def windows():
    return platform.system() == 'Windows'


def config_home(tool):
    variable = 'CODEX_HOME' if tool == 'codex' else 'CLAUDE_CONFIG_DIR'
    return Path(os.environ.get(variable) or str(Path.home() / ('.' + tool))).expanduser().absolute()


def desktop_packages():
    """Query only the current user's supported MSIX apps; never launch an app."""
    if not windows():
        return []
    powershell = Path(os.environ.get('SystemRoot', 'C:/Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    script = ("$ErrorActionPreference='Stop'; [Console]::OutputEncoding=[Text.UTF8Encoding]::new($false); "
              "$p=@(Get-AppxPackage -Name 'OpenAI.Codex'; Get-AppxPackage -Name 'Claude'); "
              "ConvertTo-Json -InputObject @($p | Select-Object Name,InstallLocation) -Compress")
    encoded = base64.b64encode(script.encode('utf-16le')).decode('ascii')
    try:
        result = subprocess.run([str(powershell), '-NoProfile', '-NonInteractive', '-EncodedCommand', encoded],
                                capture_output=True, text=True, encoding='utf-8', timeout=20,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if result.returncode:
            raise Error('PowerShell package query failed')
        data = json.loads(result.stdout.lstrip('\ufeff'))
        if not isinstance(data, list):
            raise Error('Unexpected package query response')
        return data
    except (OSError, ValueError, Error, subprocess.TimeoutExpired) as exc:
        print('Desktop package detection unavailable (' + type(exc).__name__
              + '). Use --codex-app/--claude-app for an EXE installation.', file=sys.stderr)
        return []


def discover_tools(app_paths=None):
    """Locate CLI or desktop installations without executing them or reading credentials."""
    app_paths = app_paths or {}
    found = {}
    for tool in ('codex', 'claude'):
        executable = shutil.which(tool)
        candidates = [Path(executable)] if executable else []
        if windows():
            candidates += [Path.home() / '.local/bin' / (tool + '.exe')]
            if tool == 'codex':
                if os.environ.get('CODEX_INSTALL_DIR'):
                    candidates += [Path(os.environ['CODEX_INSTALL_DIR']) / 'codex.exe']
                if os.environ.get('LOCALAPPDATA'):
                    candidates += [Path(os.environ['LOCALAPPDATA']) / 'Programs/OpenAI/Codex/bin/codex.exe']
            if os.environ.get('APPDATA'):
                candidates += [Path(os.environ['APPDATA']) / 'npm' / (tool + '.cmd')]
        found[tool] = next((p.absolute() for p in candidates if p.is_file()), None)
    if windows():
        for tool, explicit in app_paths.items():
            if explicit is not None:
                p = Path(explicit).expanduser().absolute()
                if p.suffix.lower() != '.exe' or not p.is_file():
                    raise Error('App path must name an existing EXE: ' + str(p))
                found[tool] = p
        if not all(found.values()):
            names = {'OpenAI.Codex': 'codex', 'Claude': 'claude'}
            for package in desktop_packages():
                tool = names.get(package.get('Name')) if isinstance(package, dict) else None
                location = package.get('InstallLocation') if tool else None
                if tool and not found[tool] and isinstance(location, str) and location and Path(location).is_dir():
                    found[tool] = Path(location).absolute()
        local = Path(os.environ.get('LOCALAPPDATA') or str(Path.home() / 'AppData/Local'))
        desktop = {'codex': [local/'Programs/Codex/Codex.exe', local/'Programs/OpenAI/Codex/Codex.exe'],
                   'claude': [local/'Programs/Claude/Claude.exe', local/'AnthropicClaude/Claude.exe',
                              *sorted((local/'AnthropicClaude').glob('app-*/claude.exe'), reverse=True)]}
        for tool, candidates in desktop.items():
            if not found[tool]:
                found[tool] = next((p.absolute() for p in candidates if p.is_file()), None)
    return found


def show_tools(found):
    for tool, executable in found.items():
        print(tool + ': ' + (str(executable) if executable else 'CLI/desktop app not found')
              + '\n  Configuration: ' + str(config_home(tool)))


def runtime_root(root, version):
    return root / 'releases' / version if windows() else root / 'current'


def launcher_targets(root, bin_dir):
    if windows():
        return [(bin_dir / 'workflow-harness.cmd', 'CLI')]
    return [(bin_dir / 'workflow-harness', 'CLI'), (root / 'current', 'CURRENT')]


def windows_launcher(release):
    # cmd expands percent expressions in the invocation path before this file runs.
    paths = [sys.executable, str(release / 'lib/harness_cli.py')]
    if any(any(c in p for c in '\r\n"%') for p in paths):
        raise Error('Unsupported launcher path (percent sign, quote or newline)')
    python, script = paths
    return ('@echo off\r\nsetlocal DisableDelayedExpansion\r\nchcp 65001 >nul\r\n'
            '"' + python + '" -X utf8 "' + script + '" %* & exit /b\r\n')


def reparse_point(path):
    try:
        return bool(getattr(path.lstat(), 'st_file_attributes', 0) & 0x400)
    except FileNotFoundError:
        return False


def digest(data):
    return hashlib.sha256(data).hexdigest()


def snap(path):
    if path.is_symlink():
        return {'kind': 'link', 'target': os.readlink(path)}
    if reparse_point(path):
        raise Error('Reparse point requires manual setup: ' + str(path))
    if path.is_file():
        return {'kind': 'file', 'data': base64.b64encode(path.read_bytes()).decode(),
                'mode': 0o644 if windows() else path.stat().st_mode & 0o777}
    if path.exists():
        raise Error('Not a regular file: ' + str(path))
    return {'kind': 'missing'}


def file_snap(data, mode=0o644):
    return {'kind': 'file', 'data': base64.b64encode(data).decode(), 'mode': 0o644 if windows() else mode}


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
            if not windows():
                tmp.chmod(value['mode'])
        os.replace(tmp, path)
    finally:
        if tmp.exists() or tmp.is_symlink():
            tmp.unlink()


def safe_parent(path):
    # Do not redirect installation through a symlinked ancestor.
    for parent in path.parents:
        if parent.is_symlink() or reparse_point(parent):
            raise Error('Linked parent requires manual setup: ' + str(parent))


def load_manifest(root):
    p = root / 'manifest.json'
    safe_parent(p)
    snapshot = snap(p)
    if snapshot['kind'] not in ('file', 'missing'):
        raise Error('Manifest must be a regular file')
    if not p.exists():
        return None
    data = json.loads(p.read_text(encoding='utf-8'))
    if data.get('schema_version') != 1 or data.get('install_root') != str(root):
        raise Error('Unsupported or misplaced manifest')
    return data


def block(root, version=VERSION):
    active = runtime_root(root, version)
    return ('\n' + BEGIN + '\n'
            'Read and follow the personal workflow rules at: ' + str(active / 'rules/AGENTS.md') + '\n'
            'Harness root: ' + str(active) + '\n'
            'Before plan review, use plan_reviewer with original requirements and all project plans.\n'
            'Follow the workflow routing rules: formal work requires implementation_reviewer after checks; lightweight work uses conditional review. Use a CODE/RUN/ENV request when reviewing.\n'
            'Project plans and shared memory live at the Git repository root under .harness/.\n'
            + END + '\n')


def registrations(root, tool, version=VERSION):
    codex = config_home('codex')
    claude = config_home('claude')
    out = []
    for name in ['plan', 'implementation']:
        role = name + '-reviewer'
        instruction = ('Harness root: ' + str(runtime_root(root, version)) + '. '
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
    safe_parent(path)
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
    return {p.relative_to(source).as_posix(): digest(p.read_bytes()) for p in sorted(source.rglob('*')) if p.is_file()}


def verify_existing(root, manifest):
    for e in manifest['entries']:
        managed_check(e)
    release = root / 'releases' / manifest['version']
    safe_parent(release)
    if release.is_symlink() or reparse_point(release) or not release.is_dir() or inventory(release) != manifest['inventory']:
        raise Error('Installed release changed; restore it before update/uninstall')


def validate_source(source, version):
    if not re.fullmatch(r'v\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?', version):
        raise Error('Use a version such as v0.1.0')
    for rel in PACKAGE_FILES:
        p = source / rel
        if p.is_symlink() or reparse_point(p) or not p.is_file():
            raise Error('Missing or symlinked package file: ' + rel)
    if (source / 'VERSION').read_text(encoding='utf-8').strip() != version:
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
            {'path': str(p), 'before': b, 'after': a} for p, b, a in changes], indent=2), encoding='utf-8')
        if not windows():
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
    if windows():
        found = discover_tools({'codex': args.codex_app, 'claude': args.claude_app})
        show_tools(found)
        if not tool:
            selected = [t for t, executable in found.items() if executable]
            if not selected:
                raise Error('No supported installation found. Install Codex/Claude Code, add its CLI to PATH, or specify --codex-app/--claude-app.')
            tool = 'both' if len(selected) == 2 else selected[0]
        # Existing settings remain updateable if a CLI is temporarily unavailable.
        if not old:
            selected = ['codex', 'claude'] if tool == 'both' else [tool]
            missing = [t for t in selected if not found[t]]
            if missing:
                raise Error('Selected installation not found: ' + ', '.join(missing))
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
        expected_paths.update(str(p) for p, _ in launcher_targets(root, args.bin_dir))
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
    if release.is_symlink() or reparse_point(release):
        raise Error('Release directory cannot be a symlink')
    changes = []
    entries = []
    previous = {e['path']: e for e in old['entries']} if old else {}
    targets = []
    for t in (['codex', 'claude'] if tool == 'both' else [tool]):
        if t == 'codex':
            codex_home = config_home('codex')
            if (codex_home / 'AGENTS.override.md').exists():
                raise Error('AGENTS.override.md shadows personal rules; resolve it before installation')
        targets.extend(registrations(root, t, version))
    targets.extend(launcher_targets(root, args.bin_dir))
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
            chunk = block(root, version)
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
                if windows():
                    after = file_snap(windows_launcher(release).encode('utf-8'))
                    entry['kind'] = 'file'
                else:
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
        metadata = json.loads((stage / 'RELEASE.json').read_text(encoding='utf-8')) if (stage / 'RELEASE.json').exists() else {}
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
    if windows():
        show_tools(discover_tools({'codex': args.codex_app, 'claude': args.claude_app}))
    data = load_manifest(args.root)
    if not data:
        print('Not installed: ' + str(args.root))
        return
    print('Version: ' + data['version'] + '\nTools: ' + data['selected_tools'] + '\nRoot: ' + str(args.root))
    verify_existing(args.root, data)
    print('Managed settings and release contents: OK')


def git(repo, *parts):
    return subprocess.check_output(['git', '-C', str(repo), *parts], text=True, encoding='utf-8').strip()


def init_project(args):
    repo = Path(git(args.repo, 'rev-parse', '--show-toplevel')).resolve()
    tracked = git(repo, 'ls-files', '--', '.harness')
    if tracked:
        raise Error('Tracked .harness files; resolve manually before init')
    workspace = repo / '.harness'
    expected = ['plans', 'memory', 'memory/progress', 'memory/history']
    if workspace.is_symlink() or reparse_point(workspace) or (workspace.exists() and not workspace.is_dir()):
        raise Error('Workspace path conflict')
    for rel in expected:
        p = workspace / rel
        if p.is_symlink() or reparse_point(p) or (p.exists() and not p.is_dir()):
            raise Error('Workspace subpath conflict: ' + str(p))
    current = workspace / 'memory/current.md'
    if current.is_symlink() or reparse_point(current) or (current.exists() and not current.is_file()):
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
        current.write_text('# Current context\n\nNo work recorded yet. Read the project plans before implementation.\n', encoding='utf-8')
    result = subprocess.run(['git', '-C', str(repo), 'check-ignore', '-q', '.harness/memory/current.md'])
    if result.returncode:
        raise Error('Ignore verification failed; inspect local exclude')
    print('Workspace ready; existing plans and memory preserved.')


class HTTPSOnlyRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not newurl.lower().startswith('https://'):
            raise Error('Non-HTTPS redirect rejected')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download(url, path):
    if not url.startswith('https://'):
        raise Error('Downloads require HTTPS')
    with urllib.request.build_opener(HTTPSOnlyRedirect()).open(url, timeout=45) as response:
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
    matches = [line.split() for line in sums.read_text(encoding='utf-8').splitlines() if len(line.split()) == 2 and line.split()[1] == asset]
    if len(matches) != 1 or digest(archive.read_bytes()) != matches[0][0]:
        raise Error('Checksum mismatch')
    dst = tmp / 'payload'
    dst.mkdir()
    unpack(archive, dst)
    return dst


def main(argv=None):
    parser = argparse.ArgumentParser(description='Personal workflow installer (macOS/Windows, Python 3.9+)')
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('install', 'update', 'status', 'uninstall', 'init'):
        p = sub.add_parser(name)
        default_root = (Path(os.environ.get('LOCALAPPDATA') or str(Path.home() / 'AppData/Local')) / 'workflow-harness'
                        if windows() else Path.home() / '.local/share/workflow-harness')
        p.add_argument('--root', type=Path, default=default_root)
        p.add_argument('--dry-run', action='store_true')
        p.add_argument('--yes', action='store_true')
        if name in ('install', 'update', 'status'):
            p.add_argument('--codex-app', type=Path, help='Windows desktop EXE path if automatic detection misses it')
            p.add_argument('--claude-app', type=Path, help='Windows desktop EXE path if automatic detection misses it')
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
    if args.root.is_symlink() or reparse_point(args.root):
        raise Error('Install root cannot be a symlink')
    if hasattr(args, 'bin_dir'):
        existing = load_manifest(args.root)
        args.bin_dir = (args.bin_dir or (Path(existing['bin_dir']) if existing else
                        (args.root / 'bin' if windows() else Path.home() / '.local/bin'))).expanduser().absolute()
        if windows() and any(c in str(args.bin_dir) for c in '\r\n"%'):
            raise Error('Unsupported bin directory (percent sign, quote or newline)')
    if args.command in ('install', 'update'):
        if platform.system() not in ('Darwin', 'Windows'):
            raise Error('Supported platforms: macOS and native Windows (not Linux/WSL)')
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
