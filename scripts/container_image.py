"""Build an OCI image without a daemon; export, verify and preserve a Docker archive.

Only explicitly selected OS package files and project assets enter the image.
No namespaces, mounts, host-driver copying, credentials or security changes are used.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import stat
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[1]
OCI_MANIFEST = 'application/vnd.oci.image.manifest.v1+json'
OCI_CONFIG = 'application/vnd.oci.image.config.v1+json'
OCI_LAYER = 'application/vnd.oci.image.layer.v1.tar+gzip'


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024**2), b''):
            h.update(block)
    return h.hexdigest()


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.partial')
    temporary.write_bytes(encoded(value) + b'\n')
    temporary.replace(path)


def now():
    return datetime.now(timezone.utc).isoformat()


def safe_name(name):
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or str(path) != name or name in ('', '.'):
        raise ValueError('Unsafe image member: ' + name)
    return name


def descriptor(media, data):
    return dict(mediaType=media, digest='sha256:' + hashlib.sha256(data).hexdigest(), size=len(data))


def blob(layout, desc):
    value = desc['digest']
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', value):
        raise ValueError('Invalid blob digest')
    return Path(layout) / 'blobs/sha256' / value.split(':')[1]


def store_blob(layout, media, data):
    desc = descriptor(media, data)
    blob(layout, desc).write_bytes(data)
    return desc


class HashWriter:
    def __init__(self, target):
        self.target, self.hash, self.size = target, hashlib.sha256(), 0

    def write(self, data):
        self.hash.update(data)
        self.size += len(data)
        self.target.write(data)
        return len(data)

    def flush(self):
        self.target.flush()


class HashReader:
    def __init__(self, source):
        self.source, self.hash = source, hashlib.sha256()

    def read(self, size=-1):
        data = self.source.read(size)
        self.hash.update(data)
        return data


def add_source(entries, source, name=None):
    source = Path(source)
    name = safe_name(name or str(source).lstrip('/'))
    try:
        st = source.lstat()
    except FileNotFoundError:
        return
    if not (stat.S_ISREG(st.st_mode) or stat.S_ISDIR(st.st_mode) or stat.S_ISLNK(st.st_mode)):
        return
    if '__pycache__' in source.parts or source.suffix == '.pyc':
        return
    value = dict(source=str(source), mode=stat.S_IMODE(st.st_mode) & ~0o6000)
    if stat.S_ISLNK(st.st_mode):
        value.update(type='symlink', target=os.readlink(source))
    elif stat.S_ISDIR(st.st_mode):
        value.update(type='directory')
    else:
        value.update(type='file', bytes=st.st_size)
    if name in entries and entries[name] != value:
        # /bin and /usr/bin package records identify the same merged-/usr file.
        if not os.path.samefile(entries[name]['source'], source):
            raise ValueError('Conflicting image path: ' + name)
    else:
        entries[name] = value


def add_tree(entries, source, destination=None):
    source = Path(source)
    if not source.exists():
        raise ValueError('Missing required image input: ' + str(source))
    destination = destination or str(source).lstrip('/')
    add_source(entries, source, destination)
    for base, dirs, files in os.walk(source, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d != '__pycache__')
        for name in dirs + sorted(files):
            path = Path(base) / name
            add_source(entries, path, str(PurePosixPath(destination) / path.relative_to(source)))


def add_bytes(entries, name, data, mode=0o644):
    entries[safe_name(name)] = dict(type='file', data=data, bytes=len(data), mode=mode)


def os_inventory():
    rows = subprocess.check_output(['dpkg-query', '-W', '-f=${binary:Package}\t${Version}\t${db:Status-Status}\n'], text=True)
    packages = [dict(name=r[0], version=r[1]) for line in rows.splitlines()
                if len(r := line.split('\t')) == 3 and r[2] == 'installed']
    selected = [p['name'] for p in packages if not p['name'].startswith('cuda-compat-')]
    paths = subprocess.check_output(['dpkg-query', '-L', *selected], text=True).splitlines()
    entries = {}
    def eligible(path):
        return (path.startswith(('/usr/', '/opt/', '/bin/', '/sbin/', '/lib/', '/lib64/'))
                and '/compat/' not in path and '/firmware/nvidia/' not in path
                and not (Path(path).name.startswith(('libcuda.so', 'libnvidia-', 'libcudadebugger', 'libnvcuvid', 'nvidia-'))
                         and '/stubs/' not in path))
    def mapped(path):
        top = path.split('/')[1]
        return ('usr' + path if top in ('bin', 'sbin', 'lib', 'lib64') else path.lstrip('/'))
    for path in sorted(set(paths)):
        if eligible(path):
            add_source(entries, path, mapped(path))
    # Alternatives and linker aliases may be created by package post-install scripts.
    for base in ['/usr/bin', '/usr/sbin', '/usr/lib', '/etc/alternatives']:
        for directory, dirs, files in os.walk(base, followlinks=False):
            for name in dirs + files:
                p = Path(directory) / name
                if p.is_symlink() and (eligible(str(p)) or base == '/etc/alternatives'):
                    add_source(entries, p)
    for path in ['/bin', '/sbin', '/lib', '/lib64', '/usr/local/bin/python', '/usr/local/bin/python3',
                 '/usr/local/cuda', '/usr/local/cuda-12', '/etc/os-release', '/etc/lsb-release',
                 '/etc/nsswitch.conf', '/etc/ld.so.conf', '/etc/services', '/etc/protocols',
                 '/etc/gai.conf', '/etc/debian_version']:
        add_source(entries, path)
    for path in ['/etc/ssl/certs', '/etc/ld.so.conf.d', '/var/lib/dpkg/info']:
        add_tree(entries, path)
    add_source(entries, '/var/lib/dpkg/status')
    for name in ['dev', 'proc', 'sys', 'run', 'root', 'tmp', 'var/tmp', 'hy-netdisk/jq/project/DriveServe',
                 'hy-tmp/driveserve/models', 'hy-tmp/driveserve/build']:
        entries[name] = dict(type='directory', mode=0o1777 if name.endswith('tmp') else 0o755)
    for name, content in {
        'etc/passwd': 'root:x:0:0:root:/root:/bin/bash\nnobody:x:65534:65534:nobody:/nonexistent:/usr/sbin/nologin\n',
        'etc/group': 'root:x:0:\nnogroup:x:65534:\n',
        'etc/hosts': '127.0.0.1 localhost\n::1 localhost\n',
        'etc/resolv.conf': '', 'etc/hostname': 'driveserve\n',
    }.items():
        add_bytes(entries, name, content.encode())
    add_bytes(entries, 'opt/driveserve/system-packages.json', encoded(dict(
        packages=packages, omitted_packages=[p for p in packages if p['name'] not in selected],
        scope='Selected dpkg-owned userland files; generated service state, credentials, host drivers and global pip packages are excluded.')))
    return entries


def write_layer(layout, label, entries):
    temporary = Path(layout) / (label + '.tar.gz.partial')
    inventory = []
    with temporary.open('wb') as raw, gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0, compresslevel=1) as compressed:
        writer = HashWriter(compressed)
        with tarfile.open(fileobj=writer, mode='w|', format=tarfile.PAX_FORMAT) as archive:
            for index, (name, entry) in enumerate(sorted(entries.items())):
                safe_name(name)
                info = tarfile.TarInfo(name)
                info.uid = info.gid = info.mtime = 0
                info.mode = entry['mode']
                record = {k: v for k, v in entry.items() if k not in ('source', 'data')}
                record['path'] = name
                if entry['type'] == 'directory':
                    info.type = tarfile.DIRTYPE
                    archive.addfile(info)
                elif entry['type'] == 'symlink':
                    info.type, info.linkname = tarfile.SYMTYPE, entry['target']
                    archive.addfile(info)
                else:
                    info.size = entry['bytes']
                    stream = io.BytesIO(entry['data']) if 'data' in entry else open(entry['source'], 'rb')
                    with stream:
                        reader = HashReader(stream)
                        archive.addfile(info, reader)
                        if stream.read(1):
                            raise ValueError('Source grew while creating layer: ' + name)
                        record['sha256'] = reader.hash.hexdigest()
                inventory.append(record)
                if index and index % 5000 == 0:
                    print(json.dumps(dict(layer=label, entries=index, total=len(entries))), flush=True)
        diff_id, uncompressed = writer.hash.hexdigest(), writer.size
    desc = dict(mediaType=OCI_LAYER, digest='sha256:' + digest(temporary), size=temporary.stat().st_size)
    temporary.replace(blob(layout, desc))
    print(json.dumps(dict(layer=label, compressed_bytes=desc['size'], uncompressed_bytes=uncompressed)), flush=True)
    return desc, 'sha256:' + diff_id, uncompressed, inventory


def build(args):
    policy = json.loads((ROOT / 'containers/runtime.json').read_text())
    if platform.machine() != 'x86_64' or platform.python_version() != policy['python']:
        raise ValueError('Builder must use the recorded x86_64 Python 3.11.10 environment')
    status = subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True)
    if status:
        raise ValueError('Commit the image implementation before building from a clean checkout')
    sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    if args.directory.exists():
        raise ValueError('Choose a fresh build directory')
    if shutil.disk_usage(args.directory.parent).free < 50 * 1024**3:
        raise ValueError('Build requires at least 50 GiB of staging space; shared memory is supported for data staging')
    args.directory.mkdir()
    layout = args.directory / 'oci'
    (layout / 'blobs/sha256').mkdir(parents=True)
    layers, diffs, sizes, inventory = [], [], [], []
    reused = None
    if args.reuse_runtime:
        reused = json.loads((args.reuse_runtime / 'image-lock.json').read_text())
        if reused['policy'] != policy or len(reused['layers']) != 4:
            raise ValueError('Reused runtime policy/layer structure differs')
        verify_layout(args.reuse_runtime / 'oci', reused)
        with gzip.open(args.reuse_runtime / 'file-inventory.json.gz', 'rb') as stream:
            old_inventory = json.load(stream)
    for label in ['system', 'python', 'addons', 'project']:
        if reused and label != 'project':
            i = len(layers)
            desc = reused['layers'][i]
            shutil.copyfile(blob(args.reuse_runtime / 'oci', desc), blob(layout, desc))
            layers.append(desc); diffs.append(reused['diff_ids'][i])
            sizes.append(reused['uncompressed_layer_bytes'][i]); inventory.append(old_inventory[i])
            continue
        entries = {}
        if label == 'system':
            entries = os_inventory()
        elif label == 'python':
            add_tree(entries, policy['venv'])
        elif label == 'addons':
            for path in policy['addon_directories']:
                add_tree(entries, path)
        else:
            bundle = args.directory / 'source.bundle'
            subprocess.run(['git', 'bundle', 'create', str(bundle), 'HEAD'], cwd=ROOT, check=True)
            add_source(entries, bundle, 'opt/driveserve/source.bundle')
            for name in ['entrypoint.sh', 'check_runtime.py', 'runtime.json']:
                add_source(entries, ROOT / 'containers' / name, 'opt/driveserve/' + name)
            entries['opt/driveserve/entrypoint.sh']['mode'] = 0o755
        desc, diff, size, records = write_layer(layout, label, entries)
        layers.append(desc); diffs.append(diff); sizes.append(size)
        inventory.append(dict(layer=label, entries=records))
    env = [
        'PATH=' + policy['venv'] + '/bin:/usr/local/cuda/bin:/hy-tmp/driveserve/tools/bin:'
        '/hy-tmp/driveserve/tools/nsight-systems-2024.5/opt/nvidia/nsight-systems-cli/2024.5.1/target-linux-x64:'
        '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
        'LD_LIBRARY_PATH=/usr/local/nvidia/lib:/usr/local/nvidia/lib64',
        'CUDA_HOME=' + policy['cuda_home'], 'NVIDIA_VISIBLE_DEVICES=all',
        'NVIDIA_DRIVER_CAPABILITIES=compute,utility', 'NVIDIA_REQUIRE_CUDA=cuda>=12.4',
        'PYTHONNOUSERSITE=1', 'PYTHONDONTWRITEBYTECODE=1', 'VLLM_USE_V1=0',
        'DRIVESERVE_SOURCE_COMMIT=' + sha, 'LANG=C.UTF-8', 'LC_ALL=C.UTF-8',
    ]
    config = dict(architecture='amd64', os='linux', created=now(),
                  config=dict(Env=env, Entrypoint=['/opt/driveserve/entrypoint.sh'],
                              Cmd=['python', '/opt/driveserve/check_runtime.py'],
                              WorkingDir=policy['project_root'],
                              Labels={'org.opencontainers.image.title': 'DriveServe fixed runtime',
                                      'org.opencontainers.image.revision': sha,
                                      'org.opencontainers.image.source': 'https://github.com/rexsaaa/DriveServe'}),
                  rootfs=dict(type='layers', diff_ids=diffs),
                  history=[dict(created_by='DriveServe allowlisted snapshot: ' + name)
                           for name in ['system', 'python', 'addons', 'project']])
    config_desc = store_blob(layout, OCI_CONFIG, encoded(config))
    manifest = dict(schemaVersion=2, mediaType=OCI_MANIFEST, config=config_desc, layers=layers)
    manifest_desc = store_blob(layout, OCI_MANIFEST, encoded(manifest))
    tag = 'driveserve:portable-' + sha[:12]
    manifest_desc['annotations'] = {'org.opencontainers.image.ref.name': tag}
    write_json(layout / 'index.json', dict(schemaVersion=2, manifests=[manifest_desc]))
    write_json(layout / 'oci-layout', dict(imageLayoutVersion='1.0.0'))
    lock = dict(schema_version=1, source_commit=sha, tag=tag, manifest=manifest_desc,
                config=config_desc, layers=layers, diff_ids=diffs, uncompressed_layer_bytes=sizes,
                policy=policy, created_at=now(), build_method='allowlisted installed-package OCI assembly; no daemon or namespace')
    if reused:
        lock['runtime_reused_from_manifest'] = reused['manifest']['digest']
    write_json(args.directory / 'image-lock.json', lock)
    with gzip.open(args.directory / 'file-inventory.json.gz', 'wb') as out:
        out.write(encoded(inventory))
    print(json.dumps(dict(status='built', directory=str(args.directory), tag=tag, manifest=manifest_desc['digest'])), flush=True)


def verify_layout(layout, lock):
    layout = Path(layout)
    if json.loads((layout / 'oci-layout').read_text()) != {'imageLayoutVersion': '1.0.0'}:
        raise ValueError('Unsupported OCI layout')
    if json.loads((layout / 'index.json').read_text()) != {'schemaVersion': 2, 'manifests': [lock['manifest']]}:
        raise ValueError('OCI index differs from the lock')
    manifest = json.loads(blob(layout, lock['manifest']).read_bytes())
    config = json.loads(blob(layout, manifest['config']).read_bytes())
    if manifest['config'] != lock['config'] or manifest['layers'] != lock['layers'] or config['rootfs']['diff_ids'] != lock['diff_ids']:
        raise ValueError('Image metadata differs from the lock')
    for desc in [lock['manifest'], manifest['config'], *manifest['layers']]:
        path = blob(layout, desc)
        if path.stat().st_size != desc['size'] or digest(path) != desc['digest'].split(':')[1]:
            raise ValueError('Blob checksum mismatch: ' + str(path))
    for i, desc in enumerate(manifest['layers']):
        h = hashlib.sha256(); size = 0
        with gzip.open(blob(layout, desc), 'rb') as stream:
            for chunk in iter(lambda: stream.read(8 * 1024**2), b''):
                h.update(chunk); size += len(chunk)
        if 'sha256:' + h.hexdigest() != lock['diff_ids'][i] or size != lock['uncompressed_layer_bytes'][i]:
            raise ValueError('Uncompressed layer differs')
    return manifest, config


@contextmanager
def gzip_output(raw, pigz=None):
    if not pigz:
        with gzip.GzipFile(filename='', mode='wb', fileobj=raw, compresslevel=1, mtime=0) as stream:
            yield stream
        return
    process = subprocess.Popen([str(pigz), '-1', '-n', '-p', '8'], stdin=subprocess.PIPE, stdout=raw)
    try:
        yield process.stdin
    finally:
        process.stdin.close()
        if process.wait() != 0:
            raise RuntimeError('Parallel gzip compression failed')


def make_archive(layout, lock, destination, pigz=None):
    if destination.exists():
        raise ValueError('Refusing to overwrite an archive')
    verify_layout(layout, lock)
    config_name = lock['config']['digest'].split(':')[1] + '.json'
    layer_names = [f'{i:03d}/layer.tar' for i in range(len(lock['layers']))]
    manifest = [dict(Config=config_name, RepoTags=[lock['tag']], Layers=layer_names)]
    with destination.open('xb') as raw, gzip_output(raw, pigz) as zipped:
        with tarfile.open(fileobj=zipped, mode='w|', format=tarfile.PAX_FORMAT) as archive:
            for name, data in [('manifest.json', encoded(manifest)),
                               (config_name, blob(layout, lock['config']).read_bytes())]:
                info = tarfile.TarInfo(name); info.size = len(data); info.mode = 0o644
                archive.addfile(info, io.BytesIO(data))
            for i, desc in enumerate(lock['layers']):
                info = tarfile.TarInfo(layer_names[i]); info.size = lock['uncompressed_layer_bytes'][i]; info.mode = 0o644
                with gzip.open(blob(layout, desc), 'rb') as stream:
                    archive.addfile(info, stream)
                print(json.dumps(dict(archive_layer=i + 1, total=len(layer_names))), flush=True)
    return dict(bytes=destination.stat().st_size, sha256=digest(destination))


def verify_archive(path, lock):
    config_name = lock['config']['digest'].split(':')[1] + '.json'
    expected = {'manifest.json', config_name, *[f'{i:03d}/layer.tar' for i in range(len(lock['layers']))]}
    seen = set()
    with tarfile.open(path, 'r|gz') as archive:
        for member in archive:
            safe_name(member.name)
            if member.name not in expected or member.name in seen or not member.isfile():
                raise ValueError('Unexpected or duplicate Docker archive entry')
            seen.add(member.name)
            with archive.extractfile(member) as stream:
                if member.name == 'manifest.json':
                    manifest = json.load(stream)
                    wanted = [dict(Config=config_name, RepoTags=[lock['tag']],
                                   Layers=[f'{i:03d}/layer.tar' for i in range(len(lock['layers']))])]
                    if manifest != wanted:
                        raise ValueError('Docker manifest differs')
                else:
                    h = hashlib.sha256()
                    for block in iter(lambda: stream.read(8 * 1024**2), b''):
                        h.update(block)
                    if member.name == config_name:
                        wanted_hash = config_name[:-5]
                        expected_size = lock['config']['size']
                    else:
                        i = int(member.name.split('/')[0])
                        wanted_hash = lock['diff_ids'][i].split(':')[1]
                        expected_size = lock['uncompressed_layer_bytes'][i]
                    if h.hexdigest() != wanted_hash or member.size != expected_size:
                        raise ValueError('Docker layer/config checksum mismatch')
    if seen != expected:
        raise ValueError('Incomplete Docker image archive')


def oss_copy(source, destination, log):
    with Path(log).open('w') as out:
        subprocess.run(['oss', 'cp', str(source), str(destination), '-p=2'], input=b'n\n',
                       stdout=out, stderr=subprocess.STDOUT, check=True)


def backup(args):
    lock = json.loads(args.lock.read_text())
    if not args.prefix.startswith('oss://DriveServe/container-images/'):
        raise ValueError('Use a dedicated project container-images prefix')
    if args.receipt.exists():
        raise ValueError('Receipt exists; verify and reuse it instead of overwriting')
    verify_archive(args.archive, lock)
    size, sha = args.archive.stat().st_size, digest(args.archive)
    uri = args.prefix.rstrip('/') + '/driveserve-' + sha[:16] + '.docker.tar.gz'
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    readback = args.archive.with_name(args.archive.name + '.readback')
    if readback.exists() or shutil.disk_usage(readback.parent).free < size + 1024**3:
        raise ValueError('Readback destination occupied or insufficient space')
    oss_copy(args.archive, uri, args.receipt.with_suffix('.upload.log'))
    oss_copy(uri, readback, args.receipt.with_suffix('.readback.log'))
    if readback.stat().st_size != size or digest(readback) != sha:
        raise ValueError('OSS image readback checksum mismatch')
    verify_archive(readback, lock)
    result = dict(schema_version=1, status='completed', verified_at=now(), object=uri,
                  bytes=size, sha256=sha, image=lock, verification='fresh full archive and every uncompressed layer/config SHA256',
                  estimated_incremental_CNY_per_day=size / 1e9 * .0004 * 24)
    write_json(args.receipt, result)
    readback.unlink()
    print(json.dumps({k: v for k, v in result.items() if k != 'image'}), flush=True)


def restore(args):
    receipt = json.loads(args.receipt.read_text())
    if receipt['status'] != 'completed' or not receipt['object'].startswith('oss://DriveServe/container-images/'):
        raise ValueError('Not a verified project image receipt')
    args.directory.mkdir(parents=True, exist_ok=True)
    archive = args.directory / (receipt['sha256'] + '.docker.tar.gz')
    if archive.exists():
        if archive.is_symlink() or digest(archive) != receipt['sha256']:
            raise ValueError('Existing archive differs; refusing to replace it')
    else:
        if shutil.disk_usage(args.directory).free < receipt['bytes'] + 1024**3:
            raise ValueError('Insufficient download space')
        temporary = archive.with_suffix('.partial')
        if temporary.exists():
            raise ValueError('Partial download exists; choose a fresh destination')
        oss_copy(receipt['object'], temporary, args.directory / 'download.log')
        if temporary.stat().st_size != receipt['bytes'] or digest(temporary) != receipt['sha256']:
            raise ValueError('Downloaded image checksum mismatch')
        os.link(temporary, archive); temporary.unlink()
    verify_archive(archive, receipt['image'])
    result = dict(status='verified', object=receipt['object'], archive=str(archive), tag=receipt['image']['tag'], checked_at=now())
    if args.load:
        subprocess.run(['docker', 'load', '--input', str(archive)], check=True)
        image_id = subprocess.check_output(['docker', 'image', 'inspect', '--format', '{{.Id}}', receipt['image']['tag']], text=True).strip()
        if image_id != receipt['image']['config']['digest']:
            raise ValueError('Loaded Docker image ID differs from the locked config')
        result.update(status='loaded', image_id=image_id)
    write_json(args.directory / 'restore-report.json', result)
    print(json.dumps(result), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='command', required=True)
    p = subs.add_parser('build'); p.add_argument('--directory', type=Path, required=True)
    p.add_argument('--reuse-runtime', type=Path, help='Reuse verified system/Python/addon layers with identical policy; refresh source only')
    p = subs.add_parser('verify'); p.add_argument('--directory', type=Path, required=True)
    p = subs.add_parser('archive'); p.add_argument('--directory', type=Path, required=True); p.add_argument('--output', type=Path, required=True)
    p.add_argument('--pigz', type=Path, help='Optional pigz executable for parallel compression')
    p = subs.add_parser('backup'); p.add_argument('--archive', type=Path, required=True); p.add_argument('--lock', type=Path, required=True)
    p.add_argument('--prefix', required=True); p.add_argument('--receipt', type=Path, required=True)
    p = subs.add_parser('restore'); p.add_argument('--receipt', type=Path, required=True); p.add_argument('--directory', type=Path, required=True)
    p.add_argument('--load', action='store_true', help='Load into an already configured Docker daemon after verification')
    args = parser.parse_args()
    if args.command == 'build': build(args)
    elif args.command == 'backup': backup(args)
    elif args.command == 'restore': restore(args)
    else:
        lock = json.loads((args.directory / 'image-lock.json').read_text())
        if args.command == 'verify':
            verify_layout(args.directory / 'oci', lock)
            print(json.dumps(dict(status='passed', manifest=lock['manifest']['digest'])))
        else:
            info = make_archive(args.directory / 'oci', lock, args.output, args.pigz)
            verify_archive(args.output, lock)
            write_json(args.directory / 'archive.json', dict(path=str(args.output), **info))
            print(json.dumps(info))


if __name__ == '__main__':
    main()
