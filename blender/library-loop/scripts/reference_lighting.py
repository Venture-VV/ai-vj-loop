"""Create the requested white-footlight variant from the selected, imported scene.

No Tripo calls. Removes laser meshes, ceiling tubes and all coloured spill lights.
Replaces the HERO light cue with the reference's approx. 1.07 s white ripple:
centre -> inner pair -> dark -> outer pair -> dark. Geometry, materials, camera,
floating books, title and audio are preserved. The source .blend is never saved over.

blender -b library_loop_final.blend --python-exit-code 2 -P scripts/reference_lighting.py -- \
    --out library_loop_white_reference.blend
"""
import argparse
from array import array
import hashlib
import json
import math
from pathlib import Path
import sys
import bpy


def geometry_signature():
    result = {}
    for index in range(1, 6):
        obj = bpy.data.objects.get('TRIPO_' + str(index))
        if obj is None or obj.type != 'MESH':
            raise RuntimeError('Required imported statue missing: ' + str(index))
        coords = array('f', [0.0]) * (len(obj.data.vertices) * 3)
        obj.data.vertices.foreach_get('co', coords)
        result[obj.name] = dict(vertices_sha256=hashlib.sha256(coords.tobytes()).hexdigest(),
                               faces=len(obj.data.polygons), parent=obj.parent.name,
                               materials=[mat.name for mat in obj.data.materials],
                               matrix=[float(v) for row in obj.matrix_world for v in row])
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', default='library_loop_white_reference.blend')
    parser.add_argument('--key-watts', type=float, default=420.0)
    options = parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    if not math.isfinite(options.key_watts) or options.key_watts <= 0:
        raise RuntimeError('--key-watts must be a finite positive number')
    source = Path(bpy.data.filepath).resolve()
    output = Path(options.out).resolve()
    if not source.is_file() or output == source:
        raise RuntimeError('Load the imported source scene and choose a separate output .blend')
    root = source.parent
    (root/'out').mkdir(parents=True, exist_ok=True)
    hero = bpy.data.scenes['HERO']
    bpy.context.window.scene = hero
    hero.frame_set(1)
    before = geometry_signature()
    camera_before = (hero.camera.name, tuple(hero.camera.location), tuple(hero.camera.rotation_euler), hero.camera.data.lens)

    disabled_meshes = []
    for obj in hero.objects:
        if obj.name.startswith(('LASER_', 'GRID_')):
            obj.hide_render = True
            obj.hide_viewport = True
            disabled_meshes.append(obj.name)
    if not any(name.startswith('LASER_') for name in disabled_meshes) or not any(name.startswith('GRID_') for name in disabled_meshes):
        raise RuntimeError('Expected laser and ceiling-tube meshes were not found')
    if 'LASERS' in bpy.data.collections:
        bpy.data.collections['LASERS'].hide_render = True

    keys = [bpy.data.objects['KEY_' + str(index)] for index in range(1, 6)]
    disabled_lights = []
    for obj in hero.objects:
        if obj.type == 'LIGHT' and obj not in keys:
            obj.data.animation_data_clear()
            obj.data.energy = 0
            obj.hide_render = True
            obj.hide_viewport = True
            disabled_lights.append(obj.name)

    # Based on the measured reference, rather than the previous 130 BPM laser cue.
    # 32 frames / 30 fps = 1.0667 seconds; hard onset, exponential falloff.
    cue = {1: (20, 8, 0.85), 2: (6, 8, 0.9), 3: (0, 10, 1.0), 4: (6, 8, 0.9), 5: (20, 8, 0.85)}
    old_interpolation = bpy.context.preferences.edit.keyframe_new_interpolation_type
    bpy.context.preferences.edit.keyframe_new_interpolation_type = 'CONSTANT'
    try:
        for index, obj in enumerate(keys, 1):
            obj.hide_render = False
            obj.hide_viewport = False
            obj.data.animation_data_clear()
            obj.data.color = (1.0, 1.0, 1.0)
            onset, duration, gain = cue[index]
            watts = options.key_watts * (1.25 if index == 3 else 1.0)
            for frame in range(1, 302):
                position = (frame-1) % 300
                age = position % 32 - onset
                # Nine complete ripples, then 12 dark frames so the ten-second
                # movie returns to the centre hit without cutting an inner-pair pulse.
                value = gain * math.exp(-age / 3.2) if position < 288 and 0 <= age < duration else 0.0
                obj.data.energy = watts * value
                obj.data.keyframe_insert('energy', frame=frame)
    finally:
        bpy.context.preferences.edit.keyframe_new_interpolation_type = old_interpolation

    # Verify the complete cue and all disabled light sources before saving.
    energy = []
    for frame in range(1, 301):
        hero.frame_set(frame)
        row = dict(frame=frame, watts=[round(obj.data.energy, 6) for obj in keys])
        energy.append(row)
        assert all(tuple(obj.data.color) == (1.0,1.0,1.0) for obj in keys)
        assert all(bpy.data.objects[name].hide_render and bpy.data.objects[name].data.energy == 0 for name in disabled_lights)
        assert all(bpy.data.objects[name].hide_render for name in disabled_meshes)
    hero.frame_set(1)
    if before != geometry_signature():
        raise RuntimeError('Statue geometry, material assignment or placement changed')
    camera_after = (hero.camera.name, tuple(hero.camera.location), tuple(hero.camera.rotation_euler), hero.camera.data.lens)
    if camera_before != camera_after:
        raise RuntimeError('Camera changed')
    assert (hero.frame_start,hero.frame_end,hero.render.fps) == (1,300,30)
    assert (hero.render.resolution_x,hero.render.resolution_y,hero.cycles.samples) == (1920,744,96)
    bpy.ops.wm.save_as_mainfile(filepath=str(output))
    record = dict(source=str(source), output=str(output), lighting='white reference ripple, no ceiling tubes',
                  cycle_frames=32, cycle_seconds=32/30, complete_cycles=9, tail_dark_frames=12,
                  disabled_meshes=disabled_meshes,
                  disabled_lights=disabled_lights, key_watts=options.key_watts,
                  geometry_material_camera_preserved=True, energy_by_frame=energy)
    (root/'out/reference-lighting-validation.json').write_text(json.dumps(record,indent=2)+'\n')
    print('[reference lighting]',json.dumps({k:v for k,v in record.items() if k!='energy_by_frame'}),flush=True)


if __name__ == '__main__':
    main()
