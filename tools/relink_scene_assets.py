"""Run in Blender with a downloaded scene loaded; save a separate portable copy.

blender -b blender/library-loop/library_loop_final.blend --python-exit-code 2 \
  -P tools/relink_scene_assets.py
"""
from pathlib import Path
import bpy

root=Path(__file__).resolve().parent.parent/'blender/library-loop'
source=Path(bpy.data.filepath)
if not source.is_file():raise RuntimeError('Load a downloaded scene first')
output=source.with_name(source.stem+'_portable.blend')
if output.exists():raise RuntimeError('Portable copy already exists; preserve it or choose another name')
for sound in bpy.data.sounds:
    candidate=root/'reference'/Path(sound.filepath).name
    if not candidate.is_file():raise RuntimeError('Missing local audio: '+candidate.name)
    sound.filepath=str(candidate)
bpy.ops.wm.save_as_mainfile(filepath=str(output),relative_remap=True)
for sound in bpy.data.sounds:sound.filepath=bpy.path.relpath(sound.filepath)
bpy.ops.wm.save_as_mainfile(filepath=str(output))
print('Saved portable copy:',output)
