from pathlib import Path
import bpy

ROOT=Path(__file__).resolve().parent.parent
bpy.ops.wm.read_factory_settings(use_empty=True)
scene=bpy.context.scene
scene.frame_start=scene.frame_end=1
scene.render.resolution_x,scene.render.resolution_y,scene.render.resolution_percentage=1920,900,100
scene.render.image_settings.file_format='PNG'
scene.render.use_sequencer=True
scene.view_settings.view_transform='Standard'
scene.view_settings.look='None'
strips=scene.sequence_editor_create().strips
font=bpy.data.fonts.load(str(ROOT/'assets/fonts/Jost-Light.ttf'))
channel=1

def label(text,x,y,size=28):
    global channel
    item=strips.new_effect(name=text,type='TEXT',channel=channel,frame_start=1,length=1)
    channel+=1
    item.text,item.font,item.font_size=text,font,size
    item.location=(x/1920,y/900)
    item.alignment_x=item.anchor_x=item.anchor_y='CENTER'
    item.color=(1,1,1,1)

label('WHITE FOOTLIGHTS  /  NO LASERS  /  NO CEILING TUBES',960,868,34)
for index,(frame,title) in enumerate([(1,'CENTER'),(7,'INNER PAIR'),(21,'OUTER PAIR'),(31,'DARK PAUSE')]):
    x,top=480+(index%2)*960,838-(index//2)*418
    path=ROOT/'renders/white_reference_checks'/('f_%04d.png'%frame)
    item=strips.new_image(str(frame),str(path),channel,1,fit_method='ORIGINAL')
    channel+=1
    item.transform.scale_x=item.transform.scale_y=0.5
    item.transform.offset_x=x-960
    item.transform.offset_y=top-40-186-450
    label(title,x,top-19)
scene.render.filepath=str(ROOT/'renders/white_reference_checks_contact.png')
bpy.ops.render.render(write_still=True)
