"""Render the taskbook check frames with the unchanged final production settings."""
import json
from pathlib import Path
import runpy
import sys
import time
import bpy

ROOT = Path(__file__).resolve().parent.parent
scene = bpy.data.scenes['HERO']
assert Path(bpy.data.filepath).name == 'library_loop_final.blend'
times = []
for frame in [1, 8, 21, 166, 173, 250, 277]:
    started = time.monotonic()
    sys.argv = ['render.py', '--', '--scene', 'HERO', '--out', str(ROOT / 'renders/final_check'),
                '--start', str(frame), '--end', str(frame)]
    runpy.run_path(str(ROOT / 'scripts/render.py'), run_name='__main__')
    dest = ROOT / 'renders/final_check' / ('f_%04d.png' % frame)
    if not dest.is_file() or dest.stat().st_size == 0:
        raise RuntimeError('Check frame is missing: ' + str(frame))
    times.append(dict(frame=frame, elapsed_seconds=round(time.monotonic()-started,2), bytes=dest.stat().st_size))
    (ROOT / 'out/check-render-times.json').write_text(json.dumps(times, indent=2) + '\n')
    print('[check]', json.dumps(times[-1]), flush=True)
