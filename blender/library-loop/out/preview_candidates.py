"""Import one complete candidate set and render frame 166 without changing the source scene."""
import argparse
import json
from pathlib import Path
import runpy
import struct
import sys
import time
import bpy

ROOT = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser()
parser.add_argument('--variant', choices=['A', 'B'], required=True)
parser.add_argument('--yaw', default='-90')
parser.add_argument('--mirror', default='')
for slot in range(1,6):
    parser.add_argument('--yaw-'+str(slot),default=None)
options = parser.parse_args(sys.argv[sys.argv.index('--')+1:])
assets = [item for item in json.loads((ROOT/'tripo/assets.json').read_text())['assets'] if not item.get('optional')]
folder = ROOT/'out'/('candidate_models_'+options.variant)
folder.mkdir(parents=True, exist_ok=True)
for asset in assets:
    source = ROOT/'assets/models'/(asset['id']+('__v2' if options.variant=='B' else '')+'.glb')
    preserved_first = ROOT/'assets/models'/(asset['id']+'__v1.glb')
    if options.variant=='A' and preserved_first.is_file():
        source = preserved_first
    if not source.is_file():
        raise RuntimeError('Missing required candidate: '+source.name)
    with source.open('rb') as handle:
        header = handle.read(12)
    if len(header)!=12 or header[:4]!=b'glTF' or struct.unpack('<II',header[4:])!=(2,source.stat().st_size):
        raise RuntimeError('Invalid candidate GLB: '+source.name)
    target = folder/(asset['id']+'.glb')
    if target.is_symlink():
        if target.resolve()!=source.resolve():
            raise RuntimeError('Unexpected candidate link: '+str(target))
    elif not target.exists():
        target.symlink_to(source)
    else:
        raise RuntimeError('Candidate path is not a link: '+str(target))

started = time.monotonic()
sys.argv = ['import_tripo.py','--','--models',str(folder),'--yaw',options.yaw,'--mirror',options.mirror,'--no-save']
for slot in range(1,6):
    value=getattr(options,'yaw_'+str(slot))
    if value is not None: sys.argv += ['--yaw-'+str(slot),value]
runpy.run_path(str(ROOT/'scripts/import_tripo.py'),run_name='__main__')
for number in range(1,6):
    obj = bpy.data.objects.get('TRIPO_'+str(number))
    if obj is None or obj.type!='MESH' or len(obj.data.polygons)==0:
        raise RuntimeError('Import incomplete in slot '+str(number))
scene = bpy.data.scenes['HERO']
bpy.context.window.scene = scene
scene.frame_set(166)
blend = ROOT/('library_loop_candidate_'+options.variant+'.blend')
bpy.ops.wm.save_as_mainfile(filepath=str(blend))
sys.argv = ['render.py','--','--scene','HERO','--out',str(ROOT/'renders'/('candidate_'+options.variant)),'--start','166','--end','166']
runpy.run_path(str(ROOT/'scripts/render.py'),run_name='__main__')
print('[candidate] variant=%s elapsed=%.2fs blend=%s' % (options.variant,time.monotonic()-started,blend),flush=True)
