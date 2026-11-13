"""Four full-quality stills of the requested reference-lighting cycle."""
import runpy
import sys
import time
from pathlib import Path
import json
import bpy

ROOT=Path(__file__).resolve().parent.parent
assert Path(bpy.data.filepath).name == 'library_loop_white_reference.blend'
times=[]
for frame in [1,7,21,31]:
    started=time.monotonic()
    sys.argv=['render.py','--','--scene','HERO','--out',str(ROOT/'renders/white_reference_checks'),
              '--start',str(frame),'--end',str(frame)]
    runpy.run_path(str(ROOT/'scripts/render.py'),run_name='__main__')
    times.append(dict(frame=frame,elapsed_seconds=round(time.monotonic()-started,2)))
    (ROOT/'out/white-reference-check-times.json').write_text(json.dumps(times,indent=2)+'\n')
    print('[reference check]',times[-1],flush=True)
