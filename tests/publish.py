#!/usr/bin/env python3
"""Exercise publication and interrupted-push recovery with real Git and a local bare remote."""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('media_publisher', Path(__file__).resolve().parents[1] / 'tools/publish.py')
publisher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publisher)


class Publication(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.repo, self.remote = self.root / 'repo', self.root / 'remote.git'
        self.web, self.models = self.root / 'web', self.root / 'models'
        self.run = subprocess.run
        self.git('init', '--bare', '--initial-branch=main', str(self.remote), cwd=self.root)
        self.git('init', '--initial-branch=main', str(self.repo), cwd=self.root)
        self.git('config', 'user.name', 'Publication fixture')
        self.git('config', 'user.email', 'publication@example.invalid')
        (self.repo / '.gitignore').write_text('.publish/\n')
        self.git('add', '.gitignore')
        self.git('commit', '-m', 'Initial fixture')
        self.git('remote', 'add', 'origin', 'https://github.com/VG-prog/angalor-media.git')
        self.git('push', str(self.remote), 'main')
        images = self.web / 'application/images'
        images.mkdir(parents=True)
        for number in range(40):
            (images / (str(number) + '.png')).write_bytes(('image ' + str(number)).encode())
        self.release = '20261030T000000Z-123456789abc'
        release = self.models / 'releases' / self.release
        (release / 'index').mkdir(parents=True)
        self.model_bytes = b'Native model fixture'
        sha = hashlib.sha256(self.model_bytes).hexdigest()
        model = self.models / 'objects' / sha[:2] / sha
        model.parent.mkdir(parents=True)
        model.write_bytes(self.model_bytes)
        (release / 'index/models.json').write_text(json.dumps({'fixture.m2': [sha, len(self.model_bytes)]}))
        (release / 'release.json').write_text(json.dumps({'release': self.release}))
        (self.models / 'current').write_text(self.release)
        self.staged = []
        self.fail_after_push = False

    def git(self, *args, cwd=None):
        return self.run(['git', '-C', str(cwd or self.repo), *args], check=True,
                        capture_output=True, text=True, env=dict(os.environ, GIT_ALLOW_PROTOCOL='file')).stdout.strip()

    def dispatch(self, command, **kwargs):
        # Only redirect transport. Index, commits, object storage and fetch/push are real Git operations.
        verb = command[3]
        if verb == 'add':
            for argument in command:
                if argument.startswith('--pathspec-from-file='):
                    self.staged.append(Path(argument.split('=', 1)[1]).read_bytes().split(b'\0')[:-1])
        if verb == 'fetch':
            # remote.origin.url is multivalued: a -c override can leave the real HTTPS URL first.
            command = [*command[:3], 'fetch', str(self.remote), 'refs/heads/main:refs/remotes/origin/main']
        elif verb == 'push':
            command = [*command[:3], 'push', str(self.remote), 'main']
        result = self.run(command, env=dict(os.environ, GIT_ALLOW_PROTOCOL='file'), **kwargs)
        if verb == 'push' and self.fail_after_push:
            self.fail_after_push = False
            raise subprocess.CalledProcessError(1, command, stderr=b'Lost push acknowledgement')
        return result

    def publish(self):
        arguments = ['publish.py', '--web-root', str(self.web), '--model-root', str(self.models), '--repo', str(self.repo)]
        output = io.StringIO()
        with patch.object(sys, 'argv', arguments), patch.object(publisher.subprocess, 'run', self.dispatch), contextlib.redirect_stdout(output):
            publisher.main()
        return json.loads(output.getvalue().splitlines()[-1])

    def manifest(self):
        return json.loads(self.git('show', 'main:publication.json', cwd=self.remote))

    def test_only_changed_files_enter_git_without_shrinking_verification_or_inventory(self):
        self.publish()
        previous = self.manifest()
        self.staged.clear()
        (self.web / 'application/images/0.png').write_bytes(b'changed image')
        (self.web / 'application/images/new.json').write_text('{"map":409}')
        checked = []
        digest = publisher.digest

        def observed(file):
            checked.append(file)
            return digest(file)

        with patch.object(publisher, 'digest', observed):
            result = self.publish()
        self.assertTrue(result['complete'])
        self.assertEqual(self.staged, [[b'web/application/images/0.png', b'web/application/images/new.json']])
        self.assertEqual({p.name for p in checked if p.parent == self.web / 'application/images'},
                         {str(n) + '.png' for n in range(40)} | {'new.json'})
        current = self.manifest()
        self.assertEqual(current['count'], previous['count'] + 1)
        self.assertEqual({k for k in previous['files'] if previous['files'][k] != current['files'][k]},
                         {'web/application/images/0.png'})
        self.assertEqual(self.git('rev-parse', 'HEAD'), self.git('rev-parse', 'main', cwd=self.remote))

    def test_lost_push_acknowledgement_keeps_the_old_complete_manifest_until_recovery(self):
        self.publish()
        previous = self.manifest()
        (self.web / 'application/images/1.png').write_bytes(b'replacement')
        self.staged.clear()
        self.fail_after_push = True
        with self.assertRaises(subprocess.CalledProcessError):
            self.publish()
        self.assertEqual(self.manifest(), previous)
        count = int(self.git('rev-list', '--count', 'HEAD'))
        self.publish()
        self.assertEqual(self.staged, [[b'web/application/images/1.png'], [b'web/application/images/1.png']])
        self.assertEqual(int(self.git('rev-list', '--count', 'HEAD')), count + 1)
        self.assertEqual(self.manifest()['files']['web/application/images/1.png']['sha256'],
                         hashlib.sha256(b'replacement').hexdigest())
        self.assertEqual(self.git('diff', '--cached', '--name-only'), '')

    def test_unchanged_publication_is_verified_without_another_commit(self):
        first = self.publish()
        self.staged.clear()
        second = self.publish()
        self.assertEqual(first['commit'], second['commit'])
        self.assertTrue(second['unchanged'])
        self.assertEqual(self.staged, [])


if __name__ == '__main__':
    unittest.main()
