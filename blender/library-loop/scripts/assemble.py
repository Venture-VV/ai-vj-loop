"""
PNG sequences + music  ->  one MP4, using Blender's own video editor (no ffmpeg install needed).

    blender -b -P scripts/assemble.py -- --hero renders/hero --top renders/top --out out/library_loop.mp4
    blender -b -P scripts/assemble.py -- --hero renders/hero --out out/library_loop_hero.mp4      # hero panel only

    --layout stack|hero   stack = TOP row above HERO row, like the reference (default when --top is given)
    --audio PATH          default: reference/audio_loop.wav
    --loops N             repeat the loop N times in the file (default 1)
    --fps 30   --crf HIGH|MEDIUM|PERC_LOSSLESS|LOSSLESS

With ffmpeg the same thing is one line:
    ffmpeg -framerate 30 -i renders/top/f_%04d.png -framerate 30 -i renders/hero/f_%04d.png -i reference/audio_loop.wav \\
           -filter_complex "[0][1]vstack" -c:v libx264 -crf 16 -pix_fmt yuv420p -c:a aac -shortest out/library_loop.mp4
"""
import bpy, glob, os, sys


def args():
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    o = dict(hero=None, top=None, audio=None, out="out/library_loop.mp4", layout=None, loops="1", fps="30", crf="HIGH")
    i = 0
    while i < len(a):
        k = a[i].lstrip("-")
        if k in o and i + 1 < len(a):
            o[k] = a[i + 1]; i += 2
        else:
            i += 1
    return o


def image_strip(strips, name, files, channel, start):
    try:
        st = strips.new_image(name, files[0], channel, start, fit_method="ORIGINAL")
    except TypeError:
        st = strips.new_image(name, files[0], channel, start)
    for f in files[1:]:
        st.elements.append(os.path.basename(f))
    try:
        st.transform.scale_x = st.transform.scale_y = 1.0
    except Exception:
        pass
    return st


def main():
    o = args()
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if not o["hero"]:
        sys.exit("--hero <folder with f_0001.png ...> is required")
    hero = sorted(glob.glob(os.path.join(os.path.abspath(o["hero"]), "*.png")))
    top = sorted(glob.glob(os.path.join(os.path.abspath(o["top"]), "*.png"))) if o["top"] else []
    if not hero:
        sys.exit("no PNG frames in " + o["hero"])
    layout = o["layout"] or ("stack" if top else "hero")
    if layout == "stack" and len(top) != len(hero):
        sys.exit("stack layout needs the same number of TOP and HERO frames (%d vs %d)" % (len(top), len(hero)))
    audio = os.path.abspath(o["audio"]) if o["audio"] else os.path.join(here, "reference", "audio_loop.wav")
    loops, fps, n = int(o["loops"]), int(o["fps"]), len(hero)

    img = bpy.data.images.load(hero[0])
    w, h = img.size
    bpy.data.images.remove(img)
    gap = (int(round(h * 0.022)) // 2) * 2 if layout == "stack" else 0
    W, H = w, (2 * h + gap if layout == "stack" else h)
    W, H = W - W % 2, H - H % 2

    sc = bpy.data.scenes.new("MASTER")
    try:
        bpy.context.window.scene = sc
    except Exception:
        pass
    r = sc.render
    r.resolution_x, r.resolution_y, r.resolution_percentage = W, H, 100
    r.fps = fps
    sc.frame_start, sc.frame_end = 1, n * loops
    try:
        sc.view_settings.view_transform = "Standard"          # frames are already graded
        sc.view_settings.look = "None"
    except Exception:
        pass
    se = sc.sequence_editor_create()
    strips = se.strips if hasattr(se, "strips") else se.sequences
    for k in range(loops):
        s0 = 1 + k * n
        st = image_strip(strips, "HERO_%d" % k, hero, 2, s0)
        if layout == "stack":
            st.transform.offset_y = -(h + gap) / 2
            tt = image_strip(strips, "TOP_%d" % k, top, 3, s0)
            tt.transform.offset_y = (h + gap) / 2
        if os.path.exists(audio):
            strips.new_sound("MUSIC_%d" % k, audio, 1, s0)

    out = os.path.abspath(o["out"])
    os.makedirs(os.path.dirname(out), exist_ok=True)
    ims = r.image_settings
    try:
        ims.media_type = "VIDEO"                                # Blender 5.x
    except Exception:
        pass
    ims.file_format = "FFMPEG"
    ff = r.ffmpeg
    ff.format = "MPEG4"
    ff.codec = "H264"
    ff.constant_rate_factor = o["crf"]
    ff.ffmpeg_preset = "GOOD"
    ff.gopsize = fps
    ff.audio_codec = "AAC"
    ff.audio_bitrate = 192
    r.filepath = out
    r.use_file_extension = False
    r.use_sequencer = True
    bpy.ops.render.render(animation=True, scene=sc.name)
    print("[assemble] %s  %dx%d  %d frames  layout=%s" % (out, W, H, n * loops, layout))


main()
