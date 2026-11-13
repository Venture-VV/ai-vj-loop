"""Inspect the delivered MP4 against source PNGs and account for authored dark pauses."""
import json
from pathlib import Path
import aud
import bpy
import numpy as np

ROOT=Path(__file__).resolve().parent.parent
directory=ROOT/'renders/white_reference_full_video_qa'
directory.mkdir(parents=True,exist_ok=True)
video=ROOT/'out/library_loop_white_reference.mp4'
cue=json.loads((ROOT/'out/reference-lighting-validation.json').read_text())['energy_by_frame']
sample_frames=[1,7,21,150,173,277,300]
bpy.ops.wm.read_factory_settings(use_empty=True)
scene=bpy.context.scene
scene.render.resolution_x,scene.render.resolution_y,scene.render.resolution_percentage=1920,744,100
scene.render.fps=30
scene.frame_start,scene.frame_end=1,300
scene.render.image_settings.file_format='PNG'
scene.render.use_sequencer=True
scene.view_settings.view_transform='Standard'
scene.view_settings.look='None'
movie=scene.sequence_editor_create().strips.new_movie('WHITE FINAL MP4',str(video),1,1,fit_method='ORIGINAL')
assert movie.frame_duration==300

def pixels(path):
    image=bpy.data.images.load(str(path),check_existing=False)
    try:
        assert tuple(image.size)==(1920,744)
        data=np.empty(1920*744*4,dtype=np.float32)
        image.pixels.foreach_get(data)
        return data.reshape(-1,4)[:,:3]
    finally:
        bpy.data.images.remove(image)

comparisons=[]
for frame in sample_frames:
    scene.frame_set(frame)
    output=directory/('f_%04d.png'%frame)
    scene.render.filepath=str(output)
    bpy.ops.render.render(write_still=True)
    source=pixels(ROOT/'renders/white_reference_full'/output.name)
    decoded=pixels(output)
    error=float(np.sqrt(np.mean((source-decoded)**2)))
    if error>0.06:
        raise RuntimeError('MP4 frame differs excessively from source: frame %d RMSE=%f'%(frame,error))
    comparisons.append(dict(frame=frame,rgb_rmse_in_blender=error,source_mean=float(source.mean()),decoded_mean=float(decoded.mean())))

brightness=[]
fully_black=[]
dark_cue=[]
for frame in range(1,301):
    data=pixels(ROOT/'renders/white_reference_full'/('f_%04d.png'%frame))
    mean,maximum=float(data.mean()),float(data.max())
    expected_dark=max(cue[frame-1]['watts'])==0
    if expected_dark:
        dark_cue.append(frame)
    if not np.isfinite(data).all():
        raise RuntimeError('Nonfinite pixel data in frame '+str(frame))
    if mean<=1e-8:
        fully_black.append(frame)
        if not expected_dark:
            raise RuntimeError('Unexpected blank frame during a lit cue: '+str(frame))
    brightness.append(dict(frame=frame,mean_rgb=mean,max_rgb=maximum,expected_dark_pause=expected_dark))

sound=aud.Sound(str(video))
audio=sound.data()
if not np.isfinite(audio).all() or audio.size==0:
    raise RuntimeError('MP4 audio cannot be decoded')
rms=float(np.sqrt(np.mean(audio**2)))
if rms<=1e-6:
    raise RuntimeError('MP4 audio is silent')
result=dict(png_frames_checked=300,video_sample_frames=sample_frames,frame_dimensions=[1920,744],
            unexpected_blank_frames=[],authored_dark_cue_frames=dark_cue,fully_black_frames=fully_black,
            video_sample_comparisons=comparisons,audio=dict(sample_rate=sound.specs[0],channels=sound.specs[1],
            decoded_samples=len(audio),rms=rms,peak=float(np.abs(audio).max())),frame_brightness=brightness)
(ROOT/'out/white-reference-full-qa.json').write_text(json.dumps(result,indent=2)+'\n')
print('[white final QA]',json.dumps({key:value for key,value in result.items() if key!='frame_brightness'}),flush=True)
