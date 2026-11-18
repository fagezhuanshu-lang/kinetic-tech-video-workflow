"""Package only the public source tree, with per-file and archive SHA256."""
from pathlib import Path
import argparse
import hashlib
import json
import zipfile

ROOT = Path(__file__).resolve().parents[1]
NAME = 'kinetic-tech-video-workflow'
VERSION = '1.1.0'
EXCLUDED = {'.git', '__pycache__', 'node_modules', '.venv', '.runtime', '.work', '.kinetic-tech-runtime', 'dist', 'outputs', 'inputs', 'delivery', 'demo-input', 'demo-output'}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    out=a.out.resolve()
    if out.exists():
        p.error('Use a new output directory; existing releases are preserved.')
    if out == ROOT or out.is_relative_to(ROOT):
        p.error('Output must be outside the repository.')
    files=[]
    for path in sorted(ROOT.rglob('*')):
        if not path.is_file(): continue
        relative=path.relative_to(ROOT)
        if set(relative.parts)&EXCLUDED or path.suffix.lower() in {'.pyc','.log','.zip','.mp4','.wav','.mp3','.m4a','.key','.pem'} or path.name.startswith('.env'):
            continue
        files.append((path,relative.as_posix()))
    if not any(rel=='SKILL.md' for _,rel in files):
        p.error('Skill entrypoint missing.')
    manifest={'name':NAME,'version':VERSION,'files':[{'path':rel,'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()} for path,rel in files]}
    payload=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
    out.mkdir(parents=True)
    archive=out/f'{NAME}-v{VERSION}.zip'
    with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for path,relative in files:
            z.write(path,f'{NAME}/{relative}')
        z.writestr(f'{NAME}/release-manifest.json',payload)
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
    digest=hashlib.sha256(archive.read_bytes()).hexdigest()
    (out/'release-manifest.json').write_bytes(payload)
    archive.with_suffix('.zip.sha256').write_text(digest+'  '+archive.name+'\n',encoding='ascii')
    print(json.dumps({'archive':str(archive),'files':len(files),'bytes':archive.stat().st_size,'sha256':digest},ensure_ascii=False))

if __name__=='__main__':main()
