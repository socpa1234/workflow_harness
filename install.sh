#!/bin/sh
set -eu
command -v python3 >/dev/null 2>&1 || { echo 'Python 3.9+ is required. Install python3, then retry.' >&2; exit 1; }
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' || { echo 'Python 3.9+ is required.' >&2; exit 1; }
# A checked-out or extracted distribution can be installed without a download.
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [ -f "$script_dir/lib/harness_cli.py" ]; then
    exec python3 "$script_dir/lib/harness_cli.py" install --source "$script_dir" "$@"
fi
command -v curl >/dev/null 2>&1 || { echo 'curl is required.' >&2; exit 1; }
exec python3 - "$@" <<'PY'
import hashlib, pathlib, re, subprocess, sys, tarfile, tempfile
args = sys.argv[1:]
version = next((args[i+1] for i, a in enumerate(args[:-1]) if a == '--version'), None)
if version is None:
    if sys.stdin.isatty():
        version = input('Release version (e.g. v0.1.0): ').strip()
        args += ['--version', version]
    else:
        sys.exit('Specify --version vX.Y.Z')
if not re.fullmatch(r'v\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?', version):
    sys.exit('Invalid version')
asset = 'workflow-harness-' + version + '.tar.gz'
base = 'https://github.com/socpa1234/workflow_harness/releases/download/' + version + '/'
allowed = {'VERSION', 'RELEASE.json', 'README.md', 'install.sh', 'bin/workflow-harness',
           'lib/harness_cli.py', 'rules/AGENTS.md', 'rules/governance/planning.md',
           'rules/governance/memory-writing.md', 'agents/plan-reviewer.md',
           'agents/implementation-reviewer.md', 'adapters/codex/README.md',
           'adapters/claude/README.md', '.codex/agents/plan-reviewer.toml', 'docs/installation.md'}
try:
    with tempfile.TemporaryDirectory(prefix='workflow-bootstrap-') as tmp:
        root = pathlib.Path(tmp)
        for name in (asset, 'SHA256SUMS'):
            subprocess.run(['curl', '--proto', '=https', '--proto-redir', '=https', '-fL',
                            '--connect-timeout', '15', '--max-time', '120', '--max-filesize', '25000000', base + name,
                            '-o', str(root/name)], check=True)
        matches = [line.split()[0] for line in (root/'SHA256SUMS').read_text().splitlines()
                   if len(line.split()) == 2 and line.split()[1] == asset]
        if len(matches) != 1 or hashlib.sha256((root/asset).read_bytes()).hexdigest() != matches[0]:
            sys.exit('Checksum mismatch; nothing installed')
        payload = root/'payload'
        payload.mkdir()
        with tarfile.open(root/asset, 'r:gz') as tar:
            members = tar.getmembers()
            names = [m.name for m in members]
            if set(names) != allowed or len(names) != len(allowed) or any(not m.isfile() or m.size > 5000000 for m in members) or sum(m.size for m in members) > 20000000:
                sys.exit('Unexpected release archive; nothing installed')
            for m in members:
                p = payload/m.name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(tar.extractfile(m).read())
                p.chmod(0o755 if m.name in ('bin/workflow-harness', 'install.sh') else 0o644)
        # Reopen terminal for selection/confirmation; the bootstrap's stdin holds this script.
        terminal = open('/dev/tty') if '--yes' not in args and '--dry-run' not in args else None
        try:
            sys.exit(subprocess.call([sys.executable, str(payload/'lib/harness_cli.py'),
                                      'install', '--source', str(payload)] + args, stdin=terminal))
        finally:
            if terminal:
                terminal.close()
except (OSError, ValueError, subprocess.CalledProcessError, tarfile.TarError) as exc:
    sys.exit('Download/install failed: ' + str(exc))
PY
