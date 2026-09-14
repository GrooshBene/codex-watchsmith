#!/usr/bin/env python3
"""Build only tracked release inputs from an exact Git commit; exclude agent state."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import tarfile


def build(ref, output):
    commit = subprocess.check_output(['git', 'rev-parse', ref + '^{commit}'], text=True).strip()
    def read(path):
        return subprocess.check_output(['git', 'show', commit + ':' + path])
    value = read('VERSION').decode().strip()
    if not re.fullmatch(r'\d+\.\d+\.\d+', value):
        raise ValueError('set VERSION to a stable version and commit before building a release')
    if ref.startswith('v') and ref != 'v' + value:
        raise ValueError('tag and VERSION mismatch')
    paths = subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', commit], text=True).splitlines()
    files = {p: read(p) for p in paths if p in ('VERSION', 'LICENSE', 'CONTRIBUTING.md', 'README.md', 'README.ko.md', 'install.sh', 'uninstall.sh')
             or p.startswith(('bin/', 'config/', 'docs/')) and not p.endswith(('.pyc', '.log'))}
    metadata = {'schema_version': 1, 'version': value, 'commit': commit,
                'files': {p: hashlib.sha256(data).hexdigest() for p, data in files.items()}}
    files['release.json'] = (json.dumps(metadata, indent=2) + '\n').encode()
    output.mkdir(parents=True, exist_ok=True)
    archive = output / f'codex-watchsmith-v{value}.tar.gz'
    with tarfile.open(archive, 'w:gz') as tar:
        for p, data in sorted(files.items()):
            info = tarfile.TarInfo(p); info.size = len(data); info.mode = 0o644
            tar.addfile(info, io.BytesIO(data))
    (output / 'SHA256SUMS').write_text(hashlib.sha256(archive.read_bytes()).hexdigest() + '  ' + archive.name + '\n')
    return archive


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ref', required=True)
    parser.add_argument('--output', type=Path, default=Path('dist'))
    args = parser.parse_args()
    print(build(args.ref, args.output))
