"""
Cue engine for the Library Loop relight ("sanctum").  Pure Python, no Blender imports,
so every curve can be unit-tested offline:   python3 scripts/test_cue.py

Structure borrowed from mature lighting-control projects (methods only, no code):
  * beat / bar / loop phases ............ Afterglow  rhythm.clj  (metronome, bar & phrase phase)
  * scenes with fade-in + hold .......... QLC+       chaserstep.h / function.h (Scene, Chaser)
  * closed motion curves, phase offsets,
    dimmer follows the stroke ........... QLC+       efx.cpp  (EFX::dimmerLevel, return stroke dark)
  * fast-rise / slow-decay accents ...... LedFx      effects/math.py  (ExpFilter)
  * grand master as a limiter ........... QLC+       grandmaster.h  (ValueMode Limit)
  * everything periodic in loop time .... spite/looper

All frame numbers are 1-based.  A channel is a list of N values (frame 1..N); frame N+1 must equal
frame 1, which `closure()` checks numerically.
"""
import math

FPS = 30
N = 300                     # frames in the loop (10.0 s)
BPM = 130.0                 # verified by autocorrelation of reference/audio_loop.wav (130.01)
BEAT = 60.0 / BPM           # 0.4615 s = 13.85 frames
KICK0 = 0.39                # s, first audible kick (measured 0.385-0.404; build_scene.py assumed 0.42)
BAR = 4                     # beats per bar


# ------------------------------------------------------------------------------------- clock
def kick_frame(k):
    """frame (float, 1-based) of kick k (k = 0 is the first audible kick)"""
    return 1.0 + (KICK0 + k * BEAT) * FPS


N_KICKS = int((N / FPS - KICK0) / BEAT) + 1          # 21 kicks inside the loop
KICKS = [kick_frame(k) for k in range(N_KICKS)]


def loop_phase(f):
    """0..1 over the loop; the only phase that is continuous across the seam"""
    return ((f - 1) % N) / N


def beat_phase(f):
    """0..1 since the last kick. The music is 21.67 beats long, so this jumps at the seam."""
    return (((f - 1) / FPS - KICK0) / BEAT) % 1.0


def bar_index(f):
    return int(math.floor(((f - 1) / FPS - KICK0) / (BEAT * BAR)))


# ------------------------------------------------------------------------------------- shaping
def smoothstep(a, b, x):
    if b == a:
        return 1.0 if x >= a else 0.0
    t = min(1.0, max(0.0, (x - a) / (b - a)))
    return t * t * (3.0 - 2.0 * t)


def lerp(a, b, t):
    return a + (b - a) * t


def osc(f, cycles, phase=0.0):
    """sine in 0..1 with a whole number of cycles per loop (seamless by construction)"""
    if cycles != int(cycles):
        raise ValueError("cycles per loop must be an integer, got %r" % (cycles,))
    return 0.5 + 0.5 * math.sin(2.0 * math.pi * (cycles * loop_phase(f) + phase))


def track(points, f):
    """eased piecewise curve through (frame, value) points. First point must be at frame 1,
    last at frame N+1 with the same value, so the curve closes."""
    if points[0][0] != 1 or points[-1][0] != N + 1 or abs(points[0][1] - points[-1][1]) > 1e-9:
        raise ValueError("track must run from frame 1 to N+1 and return to its start value")
    f = ((f - 1) % N) + 1
    for (fa, va), (fb, vb) in zip(points, points[1:]):
        if fa <= f <= fb:
            return lerp(va, vb, smoothstep(fa, fb, f))
    return points[-1][1]


def accent(f, rise=3.0, decay=7.0, kicks=None):
    """beat accent 0..1: eased 3-frame attack that peaks ON the kick, exponential release.
    Wraps around the loop, so the tail of the last kick carries into frame 1."""
    kicks = KICKS if kicks is None else kicks
    best = 0.0
    for fk in kicks:
        for wrap in (-N, 0, N):
            d = f - (fk + wrap)
            if d < -rise:
                v = 0.0
            elif d < 0:
                v = smoothstep(-rise, 0.0, d)
            else:
                v = math.exp(-d / decay)
            best = max(best, v)
    return best


OFFBEATS = [fk + 0.5 * BEAT * FPS for fk in KICKS]


class ExpFilter:
    """asymmetric exponential smoothing (LedFx): alpha_rise when going up, alpha_decay going down"""

    def __init__(self, alpha_rise=0.6, alpha_decay=0.15, value=None):
        if not (0.0 < alpha_rise <= 1.0 and 0.0 < alpha_decay <= 1.0):
            raise ValueError("smoothing factors must be in (0, 1]")
        self.alpha_rise, self.alpha_decay, self.value = alpha_rise, alpha_decay, value

    def update(self, x):
        if self.value is None:
            self.value = x
        else:
            a = self.alpha_rise if x > self.value else self.alpha_decay
            self.value = a * x + (1.0 - a) * self.value
        return self.value


def smooth_loop(values, alpha_rise=0.6, alpha_decay=0.15):
    """filter a looped channel; run the loop twice so the result is periodic"""
    flt = ExpFilter(alpha_rise, alpha_decay)
    out = []
    for _ in range(2):
        out = [flt.update(v) for v in values]
    return out


# ------------------------------------------------------------------------------------- scenes
class Cue:
    """one scene of the stack: from `start` every group fades (eased) to its level over `fade`
    frames and holds until the next cue. `fades` overrides the fade per group, `delay` postpones it."""

    def __init__(self, name, start, fade, levels, fades=None, delay=None):
        self.name, self.start, self.fade = name, float(start), float(fade)
        self.levels, self.fades, self.delay = dict(levels), dict(fades or {}), dict(delay or {})


class CueStack:
    def __init__(self, cues, groups):
        self.cues = sorted(cues, key=lambda c: c.start)
        self.groups = list(groups)
        for c in self.cues:
            missing = [g for g in self.groups if g not in c.levels]
            if missing:
                raise ValueError("cue %s has no level for %s" % (c.name, missing))
            if not 1 <= c.start <= N:
                raise ValueError("cue %s starts outside the loop" % c.name)

    def level(self, group, f):
        """level of `group` at frame f. Walks the stack in time order starting one loop early, so the
        value at frame 1 already contains the tail of the last cue: the stack is periodic."""
        f = ((f - 1) % N) + 1
        value = self.cues[-1].levels[group]
        for wrap in (-N, 0):
            for c in self.cues:
                s = c.start + wrap + c.delay.get(group, 0.0)
                if f < s:
                    continue
                value = lerp(value, c.levels[group], smoothstep(s, s + c.fades.get(group, c.fade), f))
        return value

    def channel(self, group):
        return [self.level(group, f) for f in range(1, N + 1)]

    def cue_at(self, f):
        f = ((f - 1) % N) + 1
        current = self.cues[-1]
        for c in self.cues:
            if c.start <= f:
                current = c
        return current.name


# ------------------------------------------------------------------------------------- effects
def stroke(f, start, length, out_frac=0.72):
    """one forward stroke + dark return (QLC+ EFX dimmer): returns (position 0..1, dimmer 0..1).
    position eases from 0 to 1 during the first `out_frac` of the window; the dimmer follows the
    stroke with a cosine and is 0 on the return."""
    p = (f - start) / length
    if p < 0.0 or p >= 1.0:
        return 0.0, 0.0
    if p < out_frac:
        q = p / out_frac
        return smoothstep(0.0, 1.0, q), math.sin(math.pi * q)
    return 1.0, 0.0


def strokes(f, starts, length, out_frac=0.72):
    """position/dimmer of whichever stroke window contains f (windows may wrap around the loop)"""
    for s in starts:
        for wrap in (-N, 0, N):
            pos, dim = stroke(f, s + wrap, length, out_frac)
            if dim > 0.0 or (0.0 <= (f - s - wrap) / length < 1.0):
                return pos, dim
    return 0.0, 0.0


# ------------------------------------------------------------------------------------- master
def limit(values, ceiling):
    """grand master in Limit mode: clamp a channel to `ceiling`"""
    return [min(v, ceiling) for v in values]


def families_active(families, threshold=0.06):
    """per frame: how many laser families are above `threshold` (families: name -> channel)"""
    return [sum(1 for ch in families.values() if ch[i] > threshold) for i in range(N)]


def enforce_family_limit(families, max_active=2, threshold=0.06):
    """grand master for the lasers: never more than `max_active` families at once.
    Returns the frames that violate the rule (the caller treats a non-empty list as a build error)."""
    return [i + 1 for i, n in enumerate(families_active(families, threshold)) if n > max_active]


def estimate_luma(channels, weights):
    """weighted sum used as a pre-render stand-in for whole-frame brightness"""
    return [sum(w * channels[g][i] for g, w in weights.items()) for i in range(N)]


# ------------------------------------------------------------------------------------- checks
def closure(values, f_next):
    """|value at frame N+1 - value at frame 1|.  `f_next` is the channel evaluated at frame N+1."""
    return abs(f_next - values[0])


def max_step(values):
    """largest frame-to-frame change, including the seam N -> 1"""
    return max(abs(values[i] - values[i - 1]) for i in range(len(values)))


def summary(values):
    mean = sum(values) / len(values)
    return dict(min=min(values), max=max(values), mean=mean, max_step=max_step(values),
                min_over_mean=(min(values) / mean if mean else 0.0))
