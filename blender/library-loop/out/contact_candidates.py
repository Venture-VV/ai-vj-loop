"""Lay out the ten actual Blender inspection renders as a labeled comparison sheet."""
from pathlib import Path
import bpy

ROOT=Path(__file__).resolve().parent.parent
directory=ROOT/'renders/sculpture_candidates'
ids=['hero_1_demon_rising','hero_2_angel_trumpet','hero_3_michael_dragon','hero_4_angel_spear','hero_5_lucifer_falling']
labels=['DEMON','TRUMPET','MICHAEL','SPEAR','LUCIFER']
bpy.ops.wm.read_factory_settings(use_empty=True)
scene=bpy.context.scene
scene.frame_start=scene.frame_end=1
scene.render.resolution_x=1500
scene.render.resolution_y=1000
scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG'
scene.render.use_sequencer=True
scene.view_settings.view_transform='Standard'
scene.view_settings.look='None'
editor=scene.sequence_editor_create()
strips=editor.strips if hasattr(editor,'strips') else editor.sequences
channel=1
font=bpy.data.fonts.load(str(ROOT/'assets/fonts/Jost-Light.ttf'))
def text_strip(name,text,x,y,size):
    global channel
    item=strips.new_effect(name=name,type='TEXT',channel=channel,frame_start=1,length=1)
    channel+=1
    item.text=text
    item.font=font
    item.font_size=size
    item.color=(1,1,1,1)
    item.location=(x,y)
    item.alignment_x='CENTER'
    item.anchor_x='CENTER'
    item.anchor_y='CENTER'
    return item
text_strip('Title','LIBRARY LOOP  /  SCULPTURE CANDIDATES',0.5,0.965,34)
for row in range(2):
    for col,(asset,label) in enumerate(zip(ids,labels)):
        stem=asset+('__v2' if row else '')
        path=directory/(stem+'.png')
        if row and asset=='hero_4_angel_spear':
            path=directory/(stem+'_corrected.png')
        if not path.is_file(): raise RuntimeError('Missing inspection render: '+path.name)
        item=strips.new_image(name=stem,filepath=str(path),channel=channel,frame_start=1,fit_method='ORIGINAL')
        channel+=1
        item.transform.scale_x=item.transform.scale_y=1/3
        item.transform.offset_x=-750+col*300+150
        item.transform.offset_y=(700 if row==0 else 260)-500
        text_strip('Label '+stem,'%d%s  %s'%(col+1,'B' if row else 'A',label),(col*300+150)/1500,0.905 if row==0 else 0.465,23)
text_strip('Footer','A = FIRST VERSION     B = SECOND VERSION     SPEAR B: FACING CORRECTED',0.5,0.035,20)
scene.render.filepath=str(ROOT/'renders/candidate_comparison.png')
bpy.ops.render.render(write_still=True)
print('[comparison]',scene.render.filepath,flush=True)
