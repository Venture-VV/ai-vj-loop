"""Render one 32-frame cue at production quality and repeat it four times for review."""
from datetime import datetime,timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import runpy
import shutil
import sys
import time
import traceback
import aud
import bpy
import numpy as np

ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT/'out'
FRAMES=ROOT/'renders/white_reference_cycle'
SEQUENCE=ROOT/'renders/white_reference_preview_sequence'
STATE=OUT/'white-reference-preview-status.json'
started=time.monotonic()
source=Path(bpy.data.filepath)
assert source.name=='library_loop_white_reference.blend'
spec=importlib.util.spec_from_file_location('render_validation',str(OUT/'render_pipeline.py'))
validation=importlib.util.module_from_spec(spec)
spec.loader.exec_module(validation)
state=dict(stage='starting',source=str(source),source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
           started_at=datetime.now(timezone.utc).isoformat(),rendered_cycle_frames=32,preview_repetitions=4,
           preview_frames=128,preview_duration_seconds=128/30,resolution=[1920,744],samples=96)

def update(**values):
    state.update(values)
    temporary=STATE.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(state,indent=2)+'\n')
    temporary.replace(STATE)
    print('[white preview]',json.dumps(state),flush=True)

try:
    FRAMES.mkdir(parents=True,exist_ok=True)
    if list(FRAMES.glob('*.png')):
        raise RuntimeError('Preview directory is already populated; inspect it before resuming')
    for number in [1,7,21,31]:
        path=ROOT/'renders/white_reference_checks'/('f_%04d.png'%number)
        validation.check_png(path)
        shutil.copy2(path,FRAMES/path.name)
    update(stage='rendering')
    sys.argv=['render.py','--','--scene','HERO','--out',str(FRAMES),'--start','1','--end','32']
    runpy.run_path(str(ROOT/'scripts/render.py'),run_name='__main__')
    expected={'f_%04d.png'%number for number in range(1,33)}
    if {p.name for p in FRAMES.glob('*.png')}!=expected:
        raise RuntimeError('One-cycle preview frame set is incomplete')
    validated=[validation.check_png(FRAMES/name) for name in sorted(expected)]
    (OUT/'white-reference-preview-frame-validation.json').write_text(json.dumps(validated,indent=2)+'\n')
    SEQUENCE.mkdir(parents=True,exist_ok=True)
    for index in range(128):
        target=SEQUENCE/('f_%04d.png'%(index+1))
        original=FRAMES/('f_%04d.png'%(index%32+1))
        if target.exists() or target.is_symlink():
            raise RuntimeError('Preview assembly destination already exists: '+target.name)
        target.symlink_to(original)
    update(stage='assembling',render_seconds=round(time.monotonic()-started,2))
    bpy.ops.wm.read_factory_settings(use_empty=True)
    video=OUT/'library_loop_white_reference_preview.mp4'
    # Repeated images, one continuous music track. Avoid overlapping 10-second
    # music strips when a one-second lighting cycle is repeated.
    sys.argv=['assemble.py','--','--hero',str(SEQUENCE),'--out',str(video)]
    runpy.run_path(str(ROOT/'scripts/assemble.py'),run_name='__main__')
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene=bpy.context.scene
    scene.render.fps=30
    movie=scene.sequence_editor_create().strips.new_movie('Preview QA',str(video),1,1,fit_method='ORIGINAL')
    assert movie.frame_duration==128
    assert (movie.elements[0].orig_width,movie.elements[0].orig_height)==(1920,744)
    sound=aud.Sound(str(video))
    data=sound.data()
    rms=float(np.sqrt(np.mean(data**2)))
    assert rms>1e-6 and np.isfinite(data).all()
    update(stage='complete',elapsed_seconds=round(time.monotonic()-started,2),video=str(video),
           video_bytes=video.stat().st_size,video_sha256=hashlib.sha256(video.read_bytes()).hexdigest(),
           audio_sample_rate=sound.specs[0],audio_channels=sound.specs[1],audio_rms=rms)
except BaseException as error:
    update(stage='failed',error=str(error),elapsed_seconds=round(time.monotonic()-started,2))
    traceback.print_exc()
    raise
