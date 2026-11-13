"""Build the chosen scene and verify the source lighting/camera animation is preserved."""
import hashlib
import json
from pathlib import Path
import runpy
import struct
import sys
import time
import bpy

ROOT = Path(__file__).resolve().parent.parent
started = time.monotonic()
choices = [(1, 'hero_1_demon_rising', 2, -90, False),
           (2, 'hero_2_angel_trumpet', 1, -90, False),
           (3, 'hero_3_michael_dragon', 2, -90, False),
           (4, 'hero_4_angel_spear', 2, 90, True),
           (5, 'hero_5_lucifer_falling', 2, -90, False)]
folder = ROOT / 'out/selected_models'
folder.mkdir(parents=True, exist_ok=True)
selection = {}
for slot, asset, variant, yaw, mirror in choices:
    source = ROOT / 'assets/models' / (asset + ('__v2' if variant == 2 else '') + '.glb')
    with source.open('rb') as handle:
        header = handle.read(12)
    if header[:4] != b'glTF' or struct.unpack('<II', header[4:]) != (2, source.stat().st_size):
        raise RuntimeError('Invalid selected GLB: ' + source.name)
    target = folder / (asset + '.glb')
    if target.is_symlink():
        if target.resolve() != source.resolve():
            raise RuntimeError('Unexpected selection link: ' + str(target))
    elif not target.exists():
        target.symlink_to(source)
    else:
        raise RuntimeError('Selection path is not a symlink: ' + str(target))
    selection[asset] = dict(slot=slot, variant=variant, source=source.name, yaw=yaw, mirror=mirror,
                            sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                            approval=('User explicitly selected second variant and accepted single-hand sword pose.'
                                      if slot == 3 else 'Selected by assistant under the user instruction to continue and render directly.'))

scene = bpy.data.scenes['HERO']
bpy.context.window.scene = scene
original_objects = list(bpy.data.objects)
original_materials = list(bpy.data.materials)
check_frames = [1, 8, 21, 166, 173, 250, 277, 300]

def values(value):
    if isinstance(value, (bool, int, float, str)):
        return value
    try:
        return [float(v) for v in value]
    except (TypeError, ValueError):
        return str(value)

def original_animation_signature():
    snapshots = []
    for frame in check_frames:
        scene.frame_set(frame)
        objects = []
        for obj in original_objects:
            entry = [obj.name, [float(v) for row in obj.matrix_world for v in row]]
            if obj.type == 'LIGHT':
                entry += [obj.data.type, float(obj.data.energy), list(obj.data.color)]
            if obj.type == 'CAMERA':
                entry += [obj.data.type, obj.data.lens, obj.data.sensor_width, obj.data.clip_start, obj.data.clip_end]
            objects.append(entry)
        materials = []
        for material in original_materials:
            if material.node_tree:
                materials.append([material.name, [[node.name, [[socket.name, values(socket.default_value)]
                    for socket in node.inputs if hasattr(socket, 'default_value')]]
                    for node in material.node_tree.nodes]])
        snapshots.append(dict(frame=frame, objects=objects, materials=materials))
    return hashlib.sha256(json.dumps(snapshots, sort_keys=True).encode()).hexdigest()

before = original_animation_signature()
sys.argv = ['import_tripo.py', '--', '--models', str(folder), '--yaw', '-90', '--yaw-4', '90', '--mirror', '4', '--no-save']
runpy.run_path(str(ROOT / 'scripts/import_tripo.py'), run_name='__main__')
after = original_animation_signature()
if before != after:
    raise RuntimeError('Original object, camera, light or material animation changed during import')

for slot, asset, variant, yaw, mirror in choices:
    obj = bpy.data.objects.get('TRIPO_' + str(slot))
    if obj is None or obj.type != 'MESH' or not obj.data.polygons:
        raise RuntimeError('Missing statue in slot ' + str(slot))
    if any(not child.hide_render for child in bpy.data.objects['SLOT_' + str(slot)].children if child.name.startswith('PROXY_')):
        raise RuntimeError('Visible placeholder in slot ' + str(slot))
    selection[asset]['faces'] = len(obj.data.polygons)

assert (scene.frame_start, scene.frame_end, scene.render.fps) == (1, 300, 30)
assert (scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage) == (1920, 744, 100)
assert scene.render.engine == 'CYCLES' and scene.cycles.samples == 96
scene.frame_set(166)
blend = ROOT / 'library_loop_final.blend'
bpy.ops.wm.save_as_mainfile(filepath=str(blend))
(ROOT / 'out/selected-candidates.json').write_text(json.dumps(selection, indent=2) + '\n')
evidence = dict(source='library_loop.blend', output=blend.name, checked_frames=check_frames,
                original_animation_sha256_before=before, original_animation_sha256_after=after,
                unchanged=True, resolution=[1920,744], fps=30, samples=96, frame_range=[1,300],
                scene='HERO', elapsed_seconds=round(time.monotonic()-started,2))
(ROOT / 'out/scene-validation.json').write_text(json.dumps(evidence, indent=2) + '\n')
print('[selected]', json.dumps(evidence), flush=True)
