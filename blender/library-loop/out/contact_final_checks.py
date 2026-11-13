"""Show all seven requested production check frames in one contact sheet."""
from pathlib import Path
import bpy

ROOT = Path(__file__).resolve().parent.parent
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.frame_start = scene.frame_end = 1
scene.render.resolution_x = 1920
scene.render.resolution_y = 1760
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = 'PNG'
scene.render.use_sequencer = True
scene.view_settings.view_transform = 'Standard'
scene.view_settings.look = 'None'
strips = scene.sequence_editor_create().strips
font = bpy.data.fonts.load(str(ROOT/'assets/fonts/Jost-Light.ttf'))
channel = 1

def label(text,x,y,size=28):
    global channel
    item = strips.new_effect(name=text,type='TEXT',channel=channel,frame_start=1,length=1)
    channel += 1
    item.text, item.font, item.font_size = text,font,size
    item.location = (x/1920,y/1760)
    item.color = (1,1,1,1)
    item.alignment_x = item.anchor_x = item.anchor_y = 'CENTER'

label('LIBRARY LOOP  /  FINAL SCENE CHECKS',960,1724,38)
frames = [(1,'CENTER'),(8,'INNER ANGELS'),(21,'OUTER FIGURES'),(166,'ALL LIT'),
          (173,'RED / BLUE'),(250,'SCAN'),(277,'FINAL HIT')]
for index,(frame,title) in enumerate(frames):
    col,row = index%2,index//2
    x,top = 480+col*960,1696-row*418
    path = ROOT/'renders/final_check'/('f_%04d.png'%frame)
    if not path.is_file() or not path.stat().st_size:
        raise RuntimeError('Missing check frame '+str(frame))
    item = strips.new_image(name=str(frame),filepath=str(path),channel=channel,frame_start=1,fit_method='ORIGINAL')
    channel += 1
    item.transform.scale_x = item.transform.scale_y = 0.5
    item.transform.offset_x = x-960
    item.transform.offset_y = top-40-186-880
    label('FRAME %03d  /  %s'%(frame,title),x,top-19)
label('1B / 2A / 3B / 4B / 5B',1440,300,32)
label('1920 x 744   /   CYCLES 96',1440,250,26)
label('ORIGINAL LIGHTING AND TIMING',1440,200,26)
scene.render.filepath = str(ROOT/'renders/final_checks_contact.png')
bpy.ops.render.render(write_still=True)
print('[checks]',scene.render.filepath,flush=True)
