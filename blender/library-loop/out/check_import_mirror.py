from pathlib import Path
import bpy,bmesh
source=Path('scripts/import_tripo.py').read_text()
namespace={'__name__':'import_test','__file__':str(Path('scripts/import_tripo.py').resolve())}
exec(compile(source.rsplit('\nmain()',1)[0],'scripts/import_tripo.py','exec'),namespace)
for mirrored in (False,True):
    bpy.ops.mesh.primitive_cube_add(size=2)
    obj=bpy.context.object
    namespace['fit'](obj,2,-90,mirrored)
    bm=bmesh.new()
    bm.from_mesh(obj.data)
    volume=bm.calc_volume(signed=True)
    bm.free()
    assert abs(volume-8)<1e-5,(mirrored,volume)
    assert min(vertex.co.z for vertex in obj.data.vertices)==0
    bpy.data.objects.remove(obj,do_unlink=True)
    print('Mirror geometry check passed:',mirrored,'outward signed volume:',volume,flush=True)
