"""Neutral inspection renders in separate temporary scenes; the movie lighting is untouched."""
import json
import argparse
import math
from pathlib import Path
import struct
import sys
import time
import bpy
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT/'renders/sculpture_candidates'
OUT.mkdir(parents=True,exist_ok=True)
parser=argparse.ArgumentParser()
parser.add_argument('--only',default='')
parser.add_argument('--yaw',type=float,default=-90)
parser.add_argument('--mirror',action='store_true')
parser.add_argument('--tag',default='')
options=parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
files = sorted((ROOT/'assets/models').glob('hero_*.glb'))
if options.only: files=[path for path in files if path.stem==options.only]
for path in files:
    dest = OUT/(path.stem+options.tag+'.png')
    if dest.is_file() and dest.stat().st_size>0:
        continue
    with path.open('rb') as handle:
        header=handle.read(12)
    if len(header)!=12 or header[:4]!=b'glTF' or struct.unpack('<II',header[4:])!=(2,path.stat().st_size):
        raise RuntimeError('Invalid GLB: '+path.name)
    started=time.monotonic()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene=bpy.context.scene
    bpy.ops.import_scene.gltf(filepath=str(path))
    meshes=[obj for obj in scene.objects if obj.type=='MESH']
    if not meshes:
        raise RuntimeError('No mesh in '+path.name)
    bpy.ops.object.select_all(action='DESELECT')
    for obj in meshes: obj.select_set(True)
    bpy.context.view_layer.objects.active=meshes[0]
    if len(meshes)>1:
        bpy.ops.object.join()
    model=bpy.context.active_object
    matrix=model.matrix_world.copy()
    model.parent=None
    model.matrix_world=Matrix.Rotation(math.radians(options.yaw),4,'Z')@matrix
    if options.mirror:
        model.matrix_world=Matrix.Diagonal(Vector((-1,1,1,1)))@model.matrix_world
    bpy.context.view_layer.update()
    corners=[model.matrix_world@Vector(corner) for corner in model.bound_box]
    low=Vector([min(p[i] for p in corners) for i in range(3)])
    high=Vector([max(p[i] for p in corners) for i in range(3)])
    model.matrix_world=Matrix.Scale(4/(high.z-low.z),4)@model.matrix_world
    bpy.context.view_layer.update()
    corners=[model.matrix_world@Vector(corner) for corner in model.bound_box]
    low=Vector([min(p[i] for p in corners) for i in range(3)])
    high=Vector([max(p[i] for p in corners) for i in range(3)])
    center=(high+low)/2
    model.location-=Vector((center.x,center.y,low.z))
    bpy.context.view_layer.update()
    material=bpy.data.materials.new('Inspection clay')
    material.use_nodes=True
    bsdf=material.node_tree.nodes.get('Principled BSDF')
    bsdf.inputs['Base Color'].default_value=(0.58,0.61,0.64,1)
    bsdf.inputs['Roughness'].default_value=0.68
    model.data.materials.clear()
    model.data.materials.append(material)
    for polygon in model.data.polygons: polygon.use_smooth=True
    for obj in list(scene.objects):
        if obj!=model: bpy.data.objects.remove(obj,do_unlink=True)
    bpy.ops.object.camera_add(location=(0,-12,2.2))
    camera=bpy.context.object
    camera.rotation_euler=(Vector((0,0,2))-camera.location).to_track_quat('-Z','Y').to_euler()
    camera.data.type='ORTHO'
    camera.data.ortho_scale=max(4.7,(high.x-low.x)*1.25*1.2)
    scene.camera=camera
    for name,location,energy,size in [('Key',(-4,-6,8),1100,5),('Fill',(4,-3,4),600,4),('Rim',(1,4,7),1000,4)]:
        data=bpy.data.lights.new(name,'AREA')
        data.energy=energy
        data.shape='DISK'
        data.size=size
        obj=bpy.data.objects.new(name,data)
        scene.collection.objects.link(obj)
        obj.location=location
        obj.rotation_euler=(Vector((0,0,2))-obj.location).to_track_quat('-Z','Y').to_euler()
    world=bpy.data.worlds.new('Inspection background')
    world.use_nodes=True
    world.node_tree.nodes['Background'].inputs['Color'].default_value=(0.045,0.055,0.07,1)
    world.node_tree.nodes['Background'].inputs['Strength'].default_value=0.5
    scene.world=world
    scene.render.engine='CYCLES'
    scene.cycles.samples=32
    scene.cycles.use_denoising=True
    preferences=bpy.context.preferences.addons['cycles'].preferences
    preferences.compute_device_type='METAL'
    preferences.get_devices()
    for device in preferences.devices: device.use=device.type=='METAL'
    scene.cycles.device='GPU'
    scene.render.resolution_x=900
    scene.render.resolution_y=1080
    scene.render.resolution_percentage=100
    scene.render.image_settings.file_format='PNG'
    scene.render.filepath=str(dest)
    bpy.ops.render.render(write_still=True)
    print('[sculpture] %s %.2fs -> %s' % (path.name,time.monotonic()-started,dest),flush=True)
print('Mesh.flip_normals available:',hasattr(bpy.types.Mesh,'flip_normals'),flush=True)
