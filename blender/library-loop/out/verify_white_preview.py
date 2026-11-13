"""Decode the actual deliverable and compare three frames with the rendered PNGs."""
import json
from pathlib import Path
import aud
import bpy
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
directory = ROOT/'renders/white_reference_video_qa'
directory.mkdir(parents=True,exist_ok=True)
video = ROOT/'out/library_loop_white_reference_preview.mp4'
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.resolution_x,scene.render.resolution_y,scene.render.resolution_percentage = 1920,744,100
scene.render.fps = 30
scene.frame_start,scene.frame_end = 1,128
scene.render.image_settings.file_format = 'PNG'
scene.render.use_sequencer = True
scene.view_settings.view_transform = 'Standard'
scene.view_settings.look = 'None'
movie = scene.sequence_editor_create().strips.new_movie('FINAL MP4',str(video),1,1,fit_method='ORIGINAL')
assert movie.frame_duration == 128

def pixels(path):
    image = bpy.data.images.load(str(path),check_existing=False)
    try:
        assert tuple(image.size) == (1920,744)
        data = np.empty(1920*744*4,dtype=np.float32)
        image.pixels.foreach_get(data)
        return data.reshape(-1,4)[:,:3]
    finally:
        bpy.data.images.remove(image)

comparisons = []
for frame in [1,7,21,31,39]:
    scene.frame_set(frame)
    output = directory/('f_%04d.png'%frame)
    scene.render.filepath = str(output)
    bpy.ops.render.render(write_still=True)
    source = pixels(ROOT/'renders/white_reference_cycle'/('f_%04d.png'%((frame-1)%32+1)))
    decoded = pixels(output)
    error = float(np.sqrt(np.mean((source-decoded)**2)))
    if error > 0.06:
        raise RuntimeError('MP4 frame differs excessively from source: frame %d RMSE=%f'%(frame,error))
    comparisons.append(dict(frame=frame,linear_rgb_rmse=error,source_mean=float(source.mean()),decoded_mean=float(decoded.mean())))

brightness = []
for frame in range(1,33):
    data = pixels(ROOT/'renders/white_reference_cycle'/('f_%04d.png'%frame))
    mean,maximum = float(data.mean()),float(data.max())
    if not np.isfinite(data).all() or mean <= 1e-8:
        raise RuntimeError('Unexpected empty/invalid frame: '+str(frame))
    brightness.append(dict(frame=frame,mean_linear_rgb=mean,max_linear_rgb=maximum))

sound = aud.Sound(str(video))
audio = sound.data()
if not np.isfinite(audio).all() or audio.size == 0:
    raise RuntimeError('MP4 audio cannot be decoded')
rms = float(np.sqrt(np.mean(audio**2)))
if rms <= 1e-6:
    raise RuntimeError('MP4 audio is silent')
result = dict(png_frames_checked=32,video_sample_frames=[1,7,21,31,39],frame_dimensions=[1920,744],unexpected_black_frames=[],
              video_sample_comparisons=comparisons,audio=dict(sample_rate=sound.specs[0],channels=sound.specs[1],
              decoded_samples=len(audio),rms=rms,peak=float(np.abs(audio).max())),frame_brightness=brightness)
(ROOT/'out/white-reference-preview-qa.json').write_text(json.dumps(result,indent=2)+'\n')
summary = {key:value for key,value in result.items() if key!='frame_brightness'}
print('[final QA]',json.dumps(summary),flush=True)
