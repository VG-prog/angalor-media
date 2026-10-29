#!/usr/bin/env python3
"""Publish the installed public media without copying account or private upload data."""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

MEDIA = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.avif', '.svg', '.ico', '.mp4',
         '.webm', '.mp3', '.ogg', '.wav', '.woff', '.woff2', '.ttf', '.otf'}
PUBLIC = ('application/images', 'application/themes', 'application/fonts',
          'application/media', 'application/modules', 'forums/styles', 'forums/images')
BATCH_BYTES = 600 * 1024 * 1024
MAX_FILE_BYTES = 100 * 1024 * 1024


def digest(file: Path) -> str:
    with file.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--web-root', required=True, type=Path)
    parser.add_argument('--model-root', required=True, type=Path)
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--git-user', default='')
    args = parser.parse_args()
    repo = args.repo.resolve()
    state = repo / '.publish'
    state.mkdir(exist_ok=True)
    owner = repo.stat()

    def git(*command: str, **kwargs):
        prefix = ['runuser', '-u', args.git_user, '--'] if args.git_user else []
        return subprocess.run(prefix + ['git', '-C', str(repo), *command],
                              check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              **kwargs).stdout

    assert git('branch', '--show-current', text=True).strip() == 'main'
    assert git('remote', 'get-url', 'origin', text=True).strip() == 'https://github.com/VG-prog/angalor-media.git'
    git('fetch', 'origin', 'main')
    # Reconcile a push whose acknowledgement was lost before generating another commit.
    remote = git('rev-parse', 'origin/main', text=True).strip()
    local = git('rev-parse', 'HEAD', text=True).strip()
    if local != remote:
        git('merge-base', '--is-ancestor', remote, local)
        git('push', 'origin', 'main')

    records: dict[str, dict] = {}
    public_roots = [(args.web_root / name).resolve() for name in PUBLIC]

    def put(source: Path, name: str, expected: str | None = None) -> None:
        if source.is_symlink():
            resolved = source.resolve(strict=True)
            # Public avatar aliases point to the same stock picture under images/avatars.
            # Materialize the picture; never follow an alias into a config or private upload.
            if not name.startswith('web/') or resolved.suffix.lower() not in MEDIA or not any(resolved.is_relative_to(p) for p in public_roots):
                raise RuntimeError('Alias leaves public media: ' + str(source))
            source = resolved
        if not source.is_file():
            raise RuntimeError('Not a regular source: ' + str(source))
        size = source.stat().st_size
        if size >= MAX_FILE_BYTES:
            raise RuntimeError('File requires a release asset: ' + name)
        sha = digest(source)
        if expected is not None and sha != expected:
            raise RuntimeError('Published source digest differs: ' + name)
        target = repo / name
        target.parent.mkdir(parents=True, exist_ok=True)
        # The repository owner must be able to commit directories created by a root exporter.
        if os.geteuid() == 0:
            parent = target.parent
            while parent != repo:
                os.chown(parent, owner.st_uid, owner.st_gid)
                parent = parent.parent
        if target.exists() and not target.samefile(source) and (target.stat().st_size != size or digest(target) != sha):
            target.unlink()
        if not target.exists():
            try:
                os.link(source, target)
            except OSError:
                shutil.copyfile(source, target)
                target.chmod(0o644)
        if not target.samefile(source) and digest(target) != sha:
            raise RuntimeError('Export digest differs: ' + name)
        records[name] = {'sha256': sha, 'bytes': size}

    for relative in PUBLIC:
        source = args.web_root / relative
        if not source.exists():
            continue
        for file in sorted(source.rglob('*')):
            if file.is_file() and file.suffix.lower() in MEDIA:
                put(file, 'web/' + file.relative_to(args.web_root).as_posix())
        print(json.dumps({'copied': relative, 'files': len(records)}), flush=True)

    release = (args.model_root / 'current').read_text().strip()
    if not re.fullmatch(r'[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}', release):
        raise RuntimeError('Invalid model release')
    release_root = args.model_root / 'releases' / release
    objects = {}
    for shard in sorted((release_root / 'index').glob('*.json')):
        for name, (sha, size) in json.loads(shard.read_text()).items():
            if not re.fullmatch(r'[0-9a-f]{64}', sha):
                raise RuntimeError('Invalid model digest')
            if sha in objects and objects[sha] != size:
                raise RuntimeError('Conflicting model size')
            objects[sha] = size
        put(shard, 'modelviewer/releases/' + release + '/index/' + shard.name)
    for i, (sha, size) in enumerate(sorted(objects.items())):
        name = 'objects/' + sha[:2] + '/' + sha
        source = args.model_root / name
        if source.stat().st_size != size:
            raise RuntimeError('Incorrect model size: ' + name)
        put(source, 'modelviewer/' + name, sha)
        if i % 10000 == 0:
            print(json.dumps({'model_objects': i, 'total': len(objects)}), flush=True)
    put(release_root / 'release.json', 'modelviewer/releases/' + release + '/release.json')
    put(args.model_root / 'current', 'modelviewer/current')
    inventory = {'created_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                 'model_release': release, 'files': records, 'count': len(records),
                 'bytes': sum(v['bytes'] for v in records.values())}
    (state / 'inventory.json').write_text(json.dumps(inventory, separators=(',', ':')) + '\n')
    published = repo / 'publication.json'
    if published.exists():
        previous = json.loads(published.read_text())
        if previous['files'] == records and previous['model_release'] == release:
            print(json.dumps({'complete': True, 'unchanged': True, 'commit': local, 'files': len(records)}), flush=True)
            return

    batch: list[str] = []
    size = 0

    def publish_batch() -> None:
        if not batch:
            return
        paths = state / 'paths'
        paths.write_bytes(b'\0'.join(p.encode() for p in batch) + b'\0')
        paths.chmod(0o644)
        git('add', '--pathspec-from-file=' + str(paths), '--pathspec-file-nul')
        changed = git('diff', '--cached', '--name-only', text=True).splitlines()
        if changed:
            git('commit', '-m', 'Publica recursos de Angalor (' + str(len(changed)) + ' archivos)')
            git('push', 'origin', 'main')
            print(json.dumps({'pushed': len(changed), 'commit': git('rev-parse', 'HEAD', text=True).strip()}), flush=True)

    for name, item in sorted(records.items()):
        if batch and size + item['bytes'] > BATCH_BYTES:
            publish_batch()
            batch, size = [], 0
        batch.append(name)
        size += item['bytes']
    publish_batch()
    target = repo / 'publication.json'
    shutil.copyfile(state / 'inventory.json', target)
    target.chmod(0o644)
    git('add', 'publication.json')
    git('commit', '-m', 'Completa el catálogo público de media')
    git('push', 'origin', 'main')
    print(json.dumps({'complete': True, 'commit': git('rev-parse', 'HEAD', text=True).strip(),
                      'files': len(records), 'bytes': inventory['bytes']}), flush=True)


if __name__ == '__main__':
    main()
