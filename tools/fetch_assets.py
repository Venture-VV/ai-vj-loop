"""Download hash-verified handoff assets and restore their original layout (Python 3.12+)."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parent.parent


def sha(path):
    with path.open('rb') as handle:return hashlib.file_digest(handle,'sha256').hexdigest()


def install_file(source,target):
    target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists() or target.is_symlink():
        if source.is_symlink():
            if target.is_symlink() and os.readlink(source)==os.readlink(target):return
        elif target.is_file() and not target.is_symlink() and sha(source)==sha(target):return
        raise RuntimeError('Local file differs; preserving your file: '+str(target))
    if source.is_symlink():target.symlink_to(os.readlink(source))
    else:shutil.copy2(source,target)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile',choices=['review','all'],default='review')
    parser.add_argument('--list',action='store_true')
    options=parser.parse_args()
    manifest=json.loads((ROOT/'docs/RELEASE_ASSETS.json').read_text())
    assets=[x for x in manifest['assets'] if options.profile=='all' or x['profile']=='review']
    print('Assets:',len(assets),'Total MiB:',round(sum(x['bytes'] for x in assets)/1024**2,1))
    if options.list:
        for item in assets:print(item['name'],item['bytes'],item['sha256'])
        return
    cache=ROOT/'.asset-cache'
    cache.mkdir(exist_ok=True)
    for item in assets:
        path=cache/item['name']
        if not path.is_file():
            with tempfile.TemporaryDirectory(dir=cache) as temporary:
                download=Path(temporary)/item['name']
                if shutil.which('gh'):
                    subprocess.run(['gh','release','download',manifest['tag'],'--repo',manifest['repository'],
                                    '--pattern',item['name'],'--dir',temporary],check=True)
                else:
                    request=Request(item['url'],headers={'User-Agent':'ai-vj-loop-asset-fetcher'})
                    with urlopen(request,timeout=60) as response,download.open('wb') as handle:
                        shutil.copyfileobj(response,handle,1024*1024)
                if download.stat().st_size!=item['bytes'] or sha(download)!=item['sha256']:
                    raise RuntimeError('Downloaded asset integrity failure: '+item['name'])
                download.replace(path)
        if path.stat().st_size!=item['bytes'] or sha(path)!=item['sha256']:
            raise RuntimeError('Cached asset integrity failure; kept for inspection: '+str(path))
        if item['name'].endswith('.tar.gz'):
            with tempfile.TemporaryDirectory(dir=cache) as temporary:
                with tarfile.open(path,'r:gz') as archive:
                    if any(not m.name.startswith('blender/library-loop/') for m in archive.getmembers()):
                        raise RuntimeError('Unexpected archive root')
                    archive.extractall(temporary,filter='data')
                for source in sorted(Path(temporary).rglob('*')):
                    if source.is_symlink() or source.is_file():install_file(source,ROOT/source.relative_to(temporary))
        else:install_file(path,ROOT/item['restore'])
        print('Verified and restored:',item['name'],flush=True)


if __name__=='__main__':main()
