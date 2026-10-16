import gzip
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

from scripts import container_image as image


class ContainerImageTests(unittest.TestCase):
    def fixture(self, base):
        layout = base / 'oci'
        (layout / 'blobs/sha256').mkdir(parents=True)
        entries = {}
        image.add_bytes(entries, 'usr/bin/example', b'fixed image payload', 0o755)
        entries['bin'] = dict(type='symlink', target='usr/bin', mode=0o777)
        layer, diff, size, _ = image.write_layer(layout, 'test', entries)
        config = image.store_blob(layout, image.OCI_CONFIG, image.encoded(dict(
            architecture='amd64', os='linux', rootfs=dict(type='layers', diff_ids=[diff]), config={})))
        manifest = image.store_blob(layout, image.OCI_MANIFEST, image.encoded(dict(
            schemaVersion=2, mediaType=image.OCI_MANIFEST, config=config, layers=[layer])))
        manifest['annotations'] = {'org.opencontainers.image.ref.name': 'driveserve:test'}
        image.write_json(layout / 'oci-layout', {'imageLayoutVersion': '1.0.0'})
        image.write_json(layout / 'index.json', {'schemaVersion': 2, 'manifests': [manifest]})
        return layout, dict(manifest=manifest, config=config, layers=[layer], diff_ids=[diff],
                            uncompressed_layer_bytes=[size], tag='driveserve:test')

    def test_portable_archive_roundtrip_preserves_real_layer_and_config(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); layout, lock = self.fixture(root)
            archive = root / 'image.tar.gz'
            image.make_archive(layout, lock, archive)
            image.verify_archive(archive, lock)
            with tarfile.open(archive) as outer:
                with tarfile.open(fileobj=outer.extractfile('000/layer.tar')) as inner:
                    self.assertEqual(inner.getmember('bin').linkname, 'usr/bin')
                    self.assertEqual(inner.extractfile('usr/bin/example').read(), b'fixed image payload')

    def test_corrupt_blob_rejected_before_export(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); layout, lock = self.fixture(root)
            image.blob(layout, lock['layers'][0]).write_bytes(b'wrong')
            with self.assertRaisesRegex(ValueError, 'checksum'):
                image.make_archive(layout, lock, root / 'image.tar.gz')

    def test_missing_archive_layer_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); layout, lock = self.fixture(root)
            archive = root / 'missing.tar.gz'
            with tarfile.open(archive, 'w:gz'):
                pass
            with self.assertRaisesRegex(ValueError, 'Incomplete'):
                image.verify_archive(archive, lock)

    def test_paths_and_altered_index_are_rejected(self):
        for value in ['../escape', '/etc/passwd', 'usr/../../escape', '.', 'usr//bin']:
            with self.assertRaises(ValueError):
                image.safe_name(value)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); layout, lock = self.fixture(root)
            image.write_json(layout / 'index.json', {'schemaVersion': 2, 'manifests': []})
            with self.assertRaisesRegex(ValueError, 'index'):
                image.verify_layout(layout, lock)


if __name__ == '__main__':
    unittest.main()
