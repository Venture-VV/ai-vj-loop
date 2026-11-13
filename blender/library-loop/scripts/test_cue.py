"""Offline checks for the cue engine and the sanctum show. No Blender, no rendering.

    python3 scripts/test_cue.py
"""
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cue                                          # noqa: E402
import sanctum_show as show                         # noqa: E402

N = cue.N


class ClockTests(unittest.TestCase):
    def test_kicks_follow_the_measured_music(self):
        self.assertEqual(len(cue.KICKS), 21)                       # 130 BPM, first kick at 0.39 s
        self.assertAlmostEqual(cue.KICKS[0], 12.7, places=1)
        self.assertAlmostEqual(cue.KICKS[1] - cue.KICKS[0], 13.846, places=2)
        self.assertLess(cue.KICKS[-1], N + 1)

    def test_loop_is_not_a_whole_number_of_beats(self):
        # the reason slow motion uses loop phase and never beat phase: 10 s = 21.67 beats
        self.assertAlmostEqual(N / cue.FPS / cue.BEAT, 21.667, places=2)
        self.assertNotAlmostEqual(cue.beat_phase(N + 1), cue.beat_phase(1), places=2)
        self.assertAlmostEqual(cue.loop_phase(N + 1), cue.loop_phase(1))

    def test_osc_needs_whole_cycles(self):
        self.assertAlmostEqual(cue.osc(1, 5), cue.osc(N + 1, 5))
        with self.assertRaises(ValueError):
            cue.osc(1, 2.5)

    def test_track_must_close(self):
        with self.assertRaises(ValueError):
            cue.track([(1, 0.0), (N + 1, 1.0)], 10)
        pts = [(1, 0.2), (100, 1.0), (N + 1, 0.2)]
        self.assertAlmostEqual(cue.track(pts, 1), cue.track(pts, N + 1))
        self.assertAlmostEqual(cue.track(pts, 100), 1.0)


class EnvelopeTests(unittest.TestCase):
    def test_accent_peaks_on_the_kick_and_never_switches(self):
        k = cue.KICKS[5]
        self.assertAlmostEqual(cue.accent(k), 1.0, places=6)
        values = [cue.accent(f) for f in range(1, N + 1)]
        self.assertLessEqual(max(values), 1.0)
        self.assertGreater(min(values), 0.0)                       # the tail of one kick reaches the next
        self.assertLess(cue.max_step(values), 0.75)                # a switch would step by 1.0

    def test_accent_wraps_the_seam(self):
        self.assertAlmostEqual(cue.accent(1), cue.accent(N + 1), places=9)

    def test_exp_filter_is_asymmetric(self):
        up = cue.ExpFilter(0.8, 0.1, value=0.0).update(1.0)
        down = cue.ExpFilter(0.8, 0.1, value=1.0).update(0.0)
        self.assertAlmostEqual(up, 0.8)
        self.assertAlmostEqual(down, 0.9)
        looped = cue.smooth_loop([1.0 if i == 0 else 0.0 for i in range(N)], 0.9, 0.2)
        self.assertGreater(looped[1], 0.5)                         # slow release
        self.assertLess(looped[-1], 1e-6)

    def test_stroke_is_dark_on_the_way_back(self):
        pos, dim = cue.stroke(10 + 0.9 * 20, 10, 20)
        self.assertEqual((pos, dim), (1.0, 0.0))
        pos, dim = cue.stroke(10 + 0.36 * 20, 10, 20)
        self.assertAlmostEqual(dim, 1.0, places=6)                 # brightest mid-stroke


class StackTests(unittest.TestCase):
    def test_stack_is_periodic_and_fades(self):
        stack = cue.CueStack([cue.Cue("a", 1, 10, {"x": 0.0}), cue.Cue("b", 100, 20, {"x": 1.0}),
                              cue.Cue("c", 280, 20, {"x": 0.0})], ["x"])
        self.assertAlmostEqual(stack.level("x", 1), stack.level("x", N + 1))
        self.assertAlmostEqual(stack.level("x", 110), 0.5)         # half way through an eased fade
        self.assertAlmostEqual(stack.level("x", 200), 1.0)
        self.assertEqual(stack.cue_at(150), "b")

    def test_missing_group_is_an_error(self):
        with self.assertRaises(ValueError):
            cue.CueStack([cue.Cue("a", 1, 10, {"x": 0.0})], ["x", "y"])


class ShowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ch = show.build()
        cls.report = show.master(cls.ch)                           # raises if the show breaks its own rules

    def test_every_channel_has_a_value_for_every_frame(self):
        for name, values in self.ch.items():
            self.assertEqual(len(values), N, name)
            self.assertTrue(all(math.isfinite(v) for v in values), name)

    def test_no_blackout(self):
        self.assertGreaterEqual(self.report["estimate"]["min_over_mean"], 0.60)
        for name in ("key_m", "key_a", "key_d", "lib_near", "lib_mid", "lib_far", "back", "rim", "glow"):
            self.assertGreater(min(self.ch[name]), 0.1, name)

    def test_keys_never_cut(self):
        for name in ("key_m", "key_a", "key_d"):
            self.assertLessEqual(cue.max_step(self.ch[name]), 0.08, name)

    def test_at_most_two_laser_families(self):
        self.assertEqual(self.report["family_violations"], [])
        fam = show.families(self.ch)
        self.assertEqual(max(sum(1 for k in fam if fam[k][i] > 0.06) for i in range(N)), 2)

    def test_lasers_are_dark_at_the_seam(self):
        for name in ("rays", "hell", "scan", "rake_in", "rake_out"):
            self.assertLess(self.ch[name][0], 1e-6, name)
            self.assertLess(self.ch[name][-1], 0.02, name)

    def test_scan_and_rake_reset_only_while_dark(self):
        for pos, level in (("scan_pos", "scan"), ("rake_in_pos", "rake_in"), ("rake_out_pos", "rake_out")):
            p, v = self.ch[pos], self.ch[level]
            for i in range(N):
                if abs(p[i] - p[i - 1]) > 0.2:                     # a jump back to the start: the line must be
                    self.assertLess(min(v[i], v[i - 1]), 0.02,     # dark on at least one side of it
                                    "%s jumps while lit at frame %d" % (pos, i + 1))

    def test_rays_open_follows_their_level(self):
        self.assertEqual(self.ch["rays_open"][0], 0.0)
        self.assertAlmostEqual(max(self.ch["rays_open"]), 1.0)

    def test_broken_show_is_rejected(self):
        bad = dict(self.ch)
        bad["key_m"] = [0.0 if 160 <= i < 163 else v for i, v in enumerate(self.ch["key_m"])]   # a 3-frame blackout
        with self.assertRaises(ValueError):
            show.master(bad)
        bad = dict(self.ch)
        bad["scan"] = [1.0] * N                                    # a third laser family, lit across the seam
        with self.assertRaises(ValueError):
            show.master(bad)


if __name__ == "__main__":
    unittest.main()
