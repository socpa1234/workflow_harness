#requires -Version 5.1
# Native Windows bootstrap. Arguments are passed through to the Python installer.
$ErrorActionPreference = 'Stop'
$installerArgs = $args
$pythonCommand = $null
$pythonPrefix = @()
foreach ($choice in @('python', 'py', 'python3')) {
    $candidate = Get-Command $choice -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $candidate) { continue }
    # Do not invoke the Microsoft Store's uninstalled Python execution alias.
    if ($candidate.Source -match '\\Microsoft\\WindowsApps\\') { continue }
    $prefix = @()
    if ($choice -eq 'py') { $prefix = @('-3') }
    try {
        & $candidate.Source @prefix -X utf8 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' *> $null
        if ($LASTEXITCODE -eq 0) {
            $pythonCommand = $candidate.Source
            $pythonPrefix = $prefix
            break
        }
    } catch { continue }
}
if (-not $pythonCommand) {
    Write-Error 'Python 3.9+ is required. Install Python for Windows and reopen PowerShell, then retry.'
    exit 1
}
# Keep this Python block ASCII and free of double quotes for Windows PowerShell 5.1 argument passing.
$bootstrap = @'
import hashlib, pathlib, re, subprocess, sys, tarfile, tempfile, urllib.request
args = sys.argv[2:]
source = pathlib.Path(sys.argv[1])
if (source / 'lib/harness_cli.py').is_file():
    sys.exit(subprocess.call([sys.executable, '-X', 'utf8', str(source / 'lib/harness_cli.py'), 'install', '--source', str(source)] + args))
version = next((args[i+1] for i, arg in enumerate(args[:-1]) if arg == '--version'), None)
if not version or not re.fullmatch(r'v\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?', version):
    sys.exit('Specify --version vX.Y.Z for a published Windows-capable release')
asset = 'workflow-harness-' + version + '.tar.gz'
base = 'https://github.com/socpa1234/workflow_harness/releases/download/' + version + '/'
allowed = {'VERSION', 'RELEASE.json', 'README.md', 'install.sh', 'bin/workflow-harness',
           'lib/harness_cli.py', 'rules/AGENTS.md', 'rules/governance/planning.md',
           'rules/governance/memory-writing.md', 'agents/plan-reviewer.md',
           'agents/implementation-reviewer.md', 'adapters/codex/README.md',
           'adapters/claude/README.md', '.codex/agents/plan-reviewer.toml', 'docs/installation.md'}
class HTTPSOnlyRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not newurl.lower().startswith('https://'):
            raise ValueError('Non-HTTPS redirect rejected')
        return super().redirect_request(req, fp, code, msg, headers, newurl)
def fetch(url, target):
    with urllib.request.build_opener(HTTPSOnlyRedirect()).open(url, timeout=45) as response:
        if not response.geturl().startswith('https://'):
            raise ValueError('Non-HTTPS redirect rejected')
        data = response.read(25000001)
        if len(data) > 25000000:
            raise ValueError('Download exceeds size limit')
        target.write_bytes(data)
try:
    with tempfile.TemporaryDirectory(prefix='workflow-bootstrap-') as tmp:
        root = pathlib.Path(tmp)
        fetch(base + asset, root / asset)
        fetch(base + 'SHA256SUMS', root / 'SHA256SUMS')
        matches = [line.split()[0] for line in (root / 'SHA256SUMS').read_text(encoding='utf-8').splitlines()
                   if len(line.split()) == 2 and line.split()[1] == asset]
        if len(matches) != 1 or hashlib.sha256((root / asset).read_bytes()).hexdigest() != matches[0]:
            raise ValueError('Checksum mismatch; nothing installed')
        payload = root / 'payload'
        payload.mkdir()
        with tarfile.open(root / asset, 'r:gz') as tar:
            members = tar.getmembers()
            names = [member.name for member in members]
            if set(names) != allowed or len(names) != len(allowed) or any(not m.isfile() or m.size > 5000000 for m in members) or sum(m.size for m in members) > 20000000:
                raise ValueError('Unexpected release archive; nothing installed')
            for member in members:
                target = payload / member.name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(tar.extractfile(member).read())
        sys.exit(subprocess.call([sys.executable, '-X', 'utf8', str(payload / 'lib/harness_cli.py'),
                                  'install', '--source', str(payload)] + args))
except (OSError, ValueError, subprocess.CalledProcessError, tarfile.TarError) as exc:
    sys.exit('Download/install failed: ' + str(exc))
'@
& $pythonCommand @pythonPrefix -X utf8 -c $bootstrap $PSScriptRoot @installerArgs
exit $LASTEXITCODE
