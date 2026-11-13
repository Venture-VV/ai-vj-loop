from pathlib import Path
import hashlib
import json
import time
import bpy
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
SCENE = bpy.data.scenes['HERO']
bpy.context.window.scene = SCENE
PREFS = bpy.context.preferences.addons['cycles'].preferences
PREFS.compute_device_type = 'METAL'
PREFS.get_devices()
GPUS = [d for d in PREFS.devices if d.type == 'METAL']
if not GPUS:
    raise RuntimeError('Required Metal GPU unavailable')
for device in PREFS.devices:
    device.use = device.type == 'METAL'
SCENE.cycles.device = 'GPU'
assert (SCENE.cycles.samples,SCENE.render.resolution_x,SCENE.render.resolution_y) == (96,1920,744)
SCENE.render.resolution_percentage = 100
SCENE.render.image_settings.file_format = 'PNG'
SCENE.render.use_file_extension = True
SCENE.render.use_persistent_data = True
SCENE.render.use_overwrite = False
DEST = ROOT/'renders/gallery_checks'
DEST.mkdir(exist_ok=True)
if list(DEST.glob('*.png')):
    raise RuntimeError('Use an empty check directory to prevent mixing scene revisions')
record = dict(blend_sha256=hashlib.sha256((ROOT/'library_loop_gallery.blend').read_bytes()).hexdigest(),
              gpu=[d.name for d in GPUS], frames=[], resolution=[1920,744], samples=96)
for frame in (1,76,151,226):
    started = time.monotonic()
    SCENE.frame_set(frame)
    path = DEST/f'f_{frame:04d}.png'
    SCENE.render.filepath = str(path)
    bpy.ops.render.render(write_still=True,scene=SCENE.name)
    image = bpy.data.images.load(str(path),check_existing=False)
    data = np.empty(1920*744*4,dtype=np.float32)
    image.pixels.foreach_get(data)
    rgb = data.reshape(744,1920,4)[...,:3][::-1]
    luma = rgb @ np.array([.2126,.7152,.0722])
    entry = dict(frame=frame,seconds=time.monotonic()-started,mean_linear_luminance=float(luma.mean()),
                 fully_clipped_fraction=float((rgb.min(axis=2)>.999).mean()),
                 near_black_fraction=float((luma<.001).mean()),
                 file=str(path),bytes=path.stat().st_size)
    # Same exposed shelf region, between the first two columns, in all frames.
    entry['shelf_mean_linear_luminance'] = float(luma[210:540,240:350].mean())
    bpy.data.images.remove(image)
    record['frames'].append(entry)
    (ROOT/'out/gallery-checks-validation.json').write_text(json.dumps(record,indent=2)+'\n')
    print('[gallery check]',json.dumps(entry),flush=True)
print('[gallery checks complete]',json.dumps(record),flush=True)
