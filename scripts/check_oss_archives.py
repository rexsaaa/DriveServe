"""Exercise real long-wheel USTAR archive and readback compatibility."""
import hashlib
import io
import json
from pathlib import Path
import tarfile
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import tempfile
from scripts.backup_models_oss import archive_size,verify_archive

name='assets/w/aiohttp-3.14.5-cp311-cp311-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl'
with tempfile.TemporaryDirectory() as temporary:
    records=[]
    for n in [0,1,511,512,513,10240]:
        payload=b'x'*n
        path=Path(temporary)/f'{n}.tar'
        member=tarfile.TarInfo(name);member.size=n
        assert len(member.tobuf(format=tarfile.USTAR_FORMAT))==512
        with tarfile.open(path,'w',format=tarfile.USTAR_FORMAT) as archive:archive.addfile(member,io.BytesIO(payload))
        assert path.stat().st_size==archive_size(n)
        verify_archive(path,name,n,hashlib.sha256(payload).hexdigest())
        records.append(dict(payload=n,archive=path.stat().st_size))
    rejected=[]
    for bad in ['x'*101,'x'*156+'/'+'y'*100]:
        try:tarfile.TarInfo(bad).tobuf(format=tarfile.USTAR_FORMAT)
        except ValueError:rejected.append(bad)
        else:raise AssertionError('invalid USTAR path accepted')
print(json.dumps(dict(status='passed',long_member_bytes=len(name),cases=records,unrepresentable_rejected=len(rejected))))
