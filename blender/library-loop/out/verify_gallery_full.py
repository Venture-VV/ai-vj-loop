"""Decode the actual golden-library movie and check all source frames for flashes/blank output."""
import json
from pathlib import Path
import aud
import bpy
import numpy as np

ROOT=Path(__file__).resolve().parent.parent
directory=ROOT/'renders/gallery_full_video_qa'
directory.mkdir(parents=True,exist_ok=True)
video=ROOT/'out/library_loop_gallery.mp4'
sample_frames=[1,76,150,151,226,277,300]
bpy.ops.wm.read_factory_settings(use_empty=True)
scene=bpy.context.scene
scene.render.resolution_x,scene.render.resolution_y,scene.render.resolution_percentage=1920,744,100
scene.render.fps=30
scene.frame_start,scene.frame_end=1,300
scene.render.image_settings.file_format='PNG'
scene.render.use_sequencer=True
scene.view_settings.view_transform='Standard'
scene.view_settings.look='None'
movie=scene.sequence_editor_create().strips.new_movie('GOLDEN LIBRARY MP4',str(video),1,1,fit_method='ORIGINAL')
assert movie.frame_duration==300


def pixels(path):
    image=bpy.data.images.load(str(path),check_existing=False)
    try:
        assert tuple(image.size)==(1920,744)
        data=np.empty(1920*744*4,dtype=np.float32)
        image.pixels.foreach_get(data)
        return data.reshape(744,1920,4)[::-1,:,:3].copy()
    finally:
        bpy.data.images.remove(image)


comparisons=[]
for frame in sample_frames:
    scene.frame_set(frame)
    output=directory/('f_%04d.png'%frame)
    scene.render.filepath=str(output)
    bpy.ops.render.render(write_still=True)
    source=pixels(ROOT/'renders/gallery_full'/output.name)
    decoded=pixels(output)
    error=float(np.sqrt(np.mean((source-decoded)**2)))
    if error>0.06:
        raise RuntimeError('MP4 differs excessively from source: frame %d RMSE=%f'%(frame,error))
    comparisons.append(dict(frame=frame,rgb_rmse_in_blender=error,source_mean=float(source.mean()),decoded_mean=float(decoded.mean())))

brightness=[]
transitions=[]
first=previous=None
for frame in range(1,301):
    data=pixels(ROOT/'renders/gallery_full'/('f_%04d.png'%frame))
    if not np.isfinite(data).all():
        raise RuntimeError('Nonfinite pixels in frame '+str(frame))
    luma=data@np.array([.2126,.7152,.0722])
    mean=float(luma.mean())
    if mean<0.05 or float((luma<.001).mean())>0.1:
        raise RuntimeError('Unexpected dark/blank frame: '+str(frame))
    if first is None:
        first=data.copy()
    if previous is not None:
        transitions.append(dict(from_frame=frame-1,to_frame=frame,rmse=float(np.sqrt(np.mean((previous-data)**2)))))
    previous=data
    brightness.append(dict(frame=frame,mean_luminance=mean,
                           shelf_mean_luminance=float(luma[210:540,240:350].mean())))
boundary=float(np.sqrt(np.mean((previous-first)**2)))
transitions.append(dict(from_frame=300,to_frame=1,rmse=boundary))
means=[x['mean_luminance'] for x in brightness]
relative_steps=[abs(a-b)/max(a,b) for a,b in zip(means,means[1:]+means[:1])]
if max(relative_steps)>0.08:
    raise RuntimeError('Unexpected abrupt brightness change: '+str(max(relative_steps)))
ordinary=[x['rmse'] for x in transitions[:-1]]
if boundary>max(ordinary)*1.5+0.01:
    raise RuntimeError('Loop boundary is worse than ordinary frame transitions: '+str(boundary))

sound=aud.Sound(str(video))
audio=sound.data()
if not np.isfinite(audio).all() or audio.size==0:
    raise RuntimeError('MP4 audio cannot be decoded')
rms=float(np.sqrt(np.mean(audio**2)))
if rms<=1e-6:
    raise RuntimeError('MP4 audio is silent')
result=dict(png_frames_checked=300,video_sample_frames=sample_frames,frame_dimensions=[1920,744],
            unexpected_blank_frames=[],max_relative_brightness_step=max(relative_steps),
            boundary_rmse=boundary,max_ordinary_transition_rmse=max(ordinary),
            video_sample_comparisons=comparisons,audio=dict(sample_rate=sound.specs[0],channels=sound.specs[1],
            decoded_samples=len(audio),rms=rms,peak=float(np.abs(audio).max())),
            frame_brightness=brightness,frame_transitions=transitions)
(ROOT/'out/gallery-full-qa.json').write_text(json.dumps(result,indent=2)+'\n')
print('[gallery final QA]',json.dumps({key:value for key,value in result.items()
                                     if key not in ('frame_brightness','frame_transitions')}),flush=True)
