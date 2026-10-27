#!/usr/bin/env python3
"""Build an allowlisted release, never include local plans or credentials."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('harness', ROOT/'lib/harness_cli.py')
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)

def build(out, allow_dirty=False):
    version = (ROOT/'VERSION').read_text(encoding='utf-8').strip()
    cli.validate_source(ROOT, version)
    commit = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
    dirty = bool(subprocess.check_output(['git', '-C', str(ROOT), 'status', '--porcelain']))
    if dirty and not allow_dirty:
        raise SystemExit('Commit the release sources first, or use --allow-dirty for local testing only.')
    out.mkdir(parents=True, exist_ok=True)
    archive = out/('workflow-harness-' + version + '.tar.gz')
    with tempfile.TemporaryDirectory(prefix='workflow-package-') as tmp:
        stage = Path(tmp)
        for rel in cli.PACKAGE_FILES:
            target = stage/rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT/rel, target)
        (stage/'RELEASE.json').write_text(json.dumps({'version': version, 'source_commit': commit,
                                                    'development_build': dirty}, indent=2)+'\n', encoding='utf-8')
        with tarfile.open(archive, 'w:gz') as tar:
            for rel in cli.PACKAGE_FILES + ['RELEASE.json']:
                tar.add(stage/rel, arcname=rel, recursive=False)
    shutil.copy2(ROOT/'install.sh', out/'install.sh')
    # Standalone asset only: keep tar members compatible with existing v0.1.2 updaters.
    shutil.copy2(ROOT/'install.ps1', out/'install.ps1')
    sums = []
    for p in [archive, out/'install.sh', out/'install.ps1']:
        sums.append(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name)
    (out/'SHA256SUMS').write_text('\n'.join(sums)+'\n', encoding='utf-8')
    print(str(archive))
    return archive

if __name__ == '__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--output', type=Path, default=ROOT/'dist')
    p.add_argument('--allow-dirty', action='store_true')
    args=p.parse_args()
    build(args.output, args.allow_dirty)
