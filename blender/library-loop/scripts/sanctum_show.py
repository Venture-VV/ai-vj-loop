"""
The "sanctum" show: palette, cue stack and effects for the relit Library Loop.
Pure Python (no Blender). `build()` returns every animated channel as a list of N per-frame values;
scripts/sanctum_lighting.py bakes them onto lights, laser materials and laser objects.

    python3 scripts/sanctum_show.py        # print the cue sheet summary and run the master checks

Design rules enforced here (a violation raises, nothing is baked):
  * no blackout: the estimated whole-frame level never drops below 60 % of its mean
  * accents are envelopes (3-frame eased attack, exponential release), never switches
  * at most two laser families are lit at the same time
  * every channel is continuous across the loop seam
"""
import math
from cue import (N, KICKS, OFFBEATS, BEAT, FPS, Cue, CueStack, accent, osc, smoothstep, lerp, track,
                 strokes, enforce_family_limit, estimate_luma, summary, max_step, kick_frame)

# ---- palette (linear RGB). Fixtures refer to these names only. -----------------------------------
PALETTE = dict(
    amber=(1.00, 0.62, 0.30),        # library practicals, ~2800 K
    ivory=(1.00, 0.93, 0.82),        # sculpture keys, ~4300 K
    cool=(0.55, 0.85, 1.00),         # rims and the gloria backlight
    laser=(0.10, 1.00, 0.75),        # scan lines and gloria rays
    laser_core=(0.72, 1.00, 0.93),   # over-exposed centre of a beam
    ember=(1.00, 0.16, 0.06),        # hell, outer bays only
    ember_core=(1.00, 0.62, 0.36),
    paper=(1.00, 0.80, 0.52),        # glow of the open books under the sculptures
)

GROUPS = ["lib", "back", "key_m", "key_a", "key_d", "rim", "book",
          "glow", "rays", "rake", "ember", "hell", "scan"]

# bars start on kicks 4, 8, 12, 16 (frames 68, 124, 179, 234); kick 20 is frame 290
F_BAR = [int(round(kick_frame(k))) for k in (0, 4, 8, 12, 16, 20)]      # [13, 68, 124, 179, 234, 290]

_base = dict(lib=.85, back=.80, key_m=.80, key_a=.80, key_d=.80, rim=.80, book=.15,
             glow=.20, rays=0.0, rake=0.0, ember=.25, hell=0.0, scan=0.0)


def _scene(**kw):
    d = dict(_base)
    d.update(kw)
    return d


CUES = [
    # the last cue of the loop: everything eases home across the seam (frames 290 .. 12)
    Cue("1 藏书", 290, 22, _scene(), fades=dict(scan=8)),
    Cue("1b 扫描线进入", 40, 28, _scene(rake=.80)),
    Cue("2 启卷", 68, 40, _scene(rim=.85, book=.70, glow=.70, rake=1.0)),
    Cue("3 荣光", 124, 40, _scene(back=.85, key_m=1.0, key_a=1.0, key_d=.85, rim=1.0, book=.70,
                                 glow=1.0, rays=1.0, rake=.25), fades=dict(rake=14)),
    Cue("4 对峙", 179, 26, _scene(key_m=.90, key_a=.85, key_d=1.0, rim=.90, book=.50, glow=.70,
                                 rays=.50, rake=0.0, ember=1.0, hell=1.0),
        fades=dict(rake=8, ember=38), delay=dict(hell=10)),
    Cue("5 审判", 234, 22, _scene(lib=.60, back=.60, key_m=.72, key_a=.72, key_d=.72, book=.30,
                                 glow=.35, rays=0.0, hell=0.0, scan=1.0),
        fades=dict(rays=12, hell=12, scan=8), delay=dict(scan=12)),
]
STACK = CueStack(CUES, GROUPS)

# estimated share of whole-frame brightness per channel (used only for the pre-render master check)
WEIGHTS = dict(lib=.30, key=.38, glow=.12, rake=.05, rays=.05, hell=.05, scan=.05)

RAKE_LEN = 2 * BEAT * FPS                                   # one sweep = two beats = 27.7 frames
RAKE_IN = [kick_frame(k) for k in range(2, 14, 2)]          # inner aisles start on even kicks
RAKE_OUT = [kick_frame(k) for k in range(3, 13, 2)]         # outer aisles one beat later
SCAN_F = (248, 288)       # the contour line travels head -> plinth between these frames


def _window(f, a, b, ramp=10):
    """1 inside [a, b] with eased edges"""
    return smoothstep(a - ramp, a, f) * (1.0 - smoothstep(b - ramp, b, f))


def build():
    lv = {g: STACK.channel(g) for g in GROUPS}
    fr = range(1, N + 1)
    ch = {}
    on = [accent(f) for f in fr]                              # kicks
    off = [accent(f, kicks=OFFBEATS) for f in fr]             # off-beats
    w4 = [_window(f, F_BAR[3], F_BAR[4]) for f in fr]         # the stand-off scene

    # library: the swell travels from the near pools to the far ones, five times per loop
    for i, name in enumerate(("lib_near", "lib_mid", "lib_far")):
        ch[name] = [lv["lib"][f - 1] * (0.90 + 0.20 * osc(f, 5, -0.18 * i)) for f in fr]
    ch["back"] = [lv["back"][f - 1] * (0.94 + 0.12 * osc(f, 5, -0.54)) for f in fr]
    # sculptures: a held key with a soft lift on every kick; in the stand-off the demons answer off-beat
    ch["key_m"] = [lv["key_m"][i] * (1.0 + 0.12 * on[i]) for i in range(N)]
    ch["key_a"] = [lv["key_a"][i] * (1.0 + 0.12 * on[i]) for i in range(N)]
    ch["key_d"] = [lv["key_d"][i] * (1.0 + 0.12 * lerp(on[i], off[i], w4[i])) for i in range(N)]
    ch["rim"] = [lv["rim"][f - 1] * (0.85 + 0.30 * osc(f, 2, 0.5)) for f in fr]
    ch["book"] = [lv["book"][i] * (1.0 + 0.10 * on[i]) for i in range(N)]
    # A gloria: backlight in the haze + two fans of rays that open like wings of light, then fold away
    ch["glow"] = [lv["glow"][i] * (1.0 + 0.06 * on[i]) for i in range(N)]
    ch["rays"] = lv["rays"]
    ch["rays_open"] = [smoothstep(0.0, 0.9, v) for v in lv["rays"]]      # 0 folded .. 1 fully spread
    # B rakes: a line slides into the depth of each side aisle, dark on the way back
    for name, starts in (("rake_in", RAKE_IN), ("rake_out", RAKE_OUT)):
        pos, val = [], []
        for f in fr:
            p, d = strokes(f, starts, RAKE_LEN)
            pos.append(p)
            val.append(lv["rake"][f - 1] * d)
        ch[name], ch[name + "_pos"] = val, pos
    # C hell: embers always glow a little behind the demons; rays only in the stand-off
    ch["ember"] = [lv["ember"][i] * (1.0 + 0.12 * off[i] * w4[i]) for i in range(N)]
    ch["hell"] = lv["hell"]
    ch["hell_sway"] = [6.0 * math.sin(2.0 * math.pi * 2 * (f - 1) / N) for f in fr]
    # D contour scan: one pass, head to plinth
    ch["scan"] = lv["scan"]
    ch["scan_pos"] = [track([(1, 0.0), (SCAN_F[0], 0.0), (SCAN_F[1], 1.0), (298, 1.0), (N + 1, 0.0)], f) for f in fr]
    # drifting haze texture inside the beams: one slow circle per loop
    ch["haze_x"] = [math.cos(2.0 * math.pi * (f - 1) / N) for f in fr]
    ch["haze_y"] = [math.sin(2.0 * math.pi * (f - 1) / N) for f in fr]
    return ch


def families(ch):
    return dict(A=ch["rays"], B=[max(a, b) for a, b in zip(ch["rake_in"], ch["rake_out"])],
                C=ch["hell"], D=ch["scan"])


def master(ch):
    """grand master checks. Returns a report; raises ValueError on any broken rule."""
    key = [(a * 1.0 + b * 0.7 + c * 0.35) / 2.05 for a, b, c in zip(ch["key_m"], ch["key_a"], ch["key_d"])]
    lib = [(a + b + c) / 3.0 for a, b, c in zip(ch["lib_near"], ch["lib_mid"], ch["lib_far"])]
    fam = families(ch)
    est = estimate_luma(dict(lib=lib, key=key, glow=ch["glow"], rake=fam["B"], rays=ch["rays"],
                             hell=ch["hell"], scan=ch["scan"]), WEIGHTS)
    s = summary(est)
    report = dict(estimate=s, family_violations=enforce_family_limit(fam),
                  seam_dark_lasers=all(fam[k][0] <= 1e-6 and fam[k][-1] <= 0.02 for k in "ABCD"),
                  max_step={k: round(max_step(v), 4) for k, v in ch.items()},
                  cues=[dict(name=c.name, start=c.start, fade=c.fade) for c in STACK.cues])
    problems = []
    if s["min_over_mean"] < 0.60:
        problems.append("estimated brightness dips to %.0f %% of its mean (floor is 60 %%)" % (100 * s["min_over_mean"]))
    if s["max_step"] / s["mean"] > 0.06:
        problems.append("estimated brightness steps %.1f %% of its mean in one frame" % (100 * s["max_step"] / s["mean"]))
    if report["family_violations"]:
        problems.append("more than two laser families lit on frames %s" % report["family_violations"][:12])
    if not report["seam_dark_lasers"]:
        problems.append("a laser family is lit across the loop seam")
    for name in ("key_m", "key_a", "key_d", "lib_near", "lib_mid", "lib_far", "back", "rim", "glow", "ember"):
        if min(ch[name]) <= 0.0:
            problems.append("%s reaches zero (blackout)" % name)
        if report["max_step"][name] > 0.08:
            problems.append("%s jumps %.3f in one frame" % (name, report["max_step"][name]))
    for name in ("rays", "hell", "scan", "rake_in", "rake_out"):
        if report["max_step"][name] > 0.30:
            problems.append("%s jumps %.3f in one frame (hard cut)" % (name, report["max_step"][name]))
    if problems:
        raise ValueError("show breaks its own rules:\n  - " + "\n  - ".join(problems))
    return report


if __name__ == "__main__":
    c = build()
    r = master(c)
    e = r["estimate"]
    print("kicks at frames:", " ".join("%.1f" % k for k in KICKS))
    for cue in STACK.cues:
        print("  cue %-14s start f%3d  fade %2d" % (cue.name, cue.start, cue.fade))
    print("estimated level: mean %.3f  min %.3f (%.0f %% of mean)  max %.3f  max step %.2f %% of mean"
          % (e["mean"], e["min"], 100 * e["min_over_mean"], e["max"], 100 * e["max_step"] / e["mean"]))
    print("laser families lit at once: max", max(sum(1 for k in "ABCD" if families(c)[k][i] > 0.06) for i in range(N)))
    print("largest per-frame steps:", {k: v for k, v in sorted(r["max_step"].items()) if v > 0.02})
