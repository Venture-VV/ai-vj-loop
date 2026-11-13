"""Run a Blender script without a Blender install, using the `bpy` module from PyPI (CPU only).

Stand-in for    blender -b [scene.blend] -P script.py -- args...
on machines such as cloud sandboxes:

    pip install --target /path/to/bpyenv bpy==5.3.0
    python3 tools/bpy_shim.py /path/to/bpyenv [scene.blend] script.py -- args...

There is no GPU here, so pass --cpu to scripts/render.py. Used for build checks, key frames and
low-resolution previews; full-resolution sequences belong on a machine with a GPU.
"""
import runpy
import sys

if len(sys.argv) < 3:
    sys.exit(__doc__)
env, rest = sys.argv[1], sys.argv[2:]
sys.path.insert(0, env)
import bpy  # noqa: E402

blend = None
if rest and rest[0].endswith(".blend"):
    blend, rest = rest[0], rest[1:]
script, extra = rest[0], rest[1:]
if blend:
    bpy.ops.wm.open_mainfile(filepath=blend, load_ui=False, use_scripts=False)
sys.argv = ["blender", "-b"] + ([blend] if blend else []) + ["-P", script] + extra
runpy.run_path(script, run_name="__main__")
