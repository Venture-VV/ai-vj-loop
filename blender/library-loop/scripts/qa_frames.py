"""Measure a rendered frame sequence against the relight acceptance criteria.

    python3 scripts/qa_frames.py renders/sanctum_full                 # needs numpy + Pillow
    blender -b -P scripts/qa_frames.py -- renders/sanctum_full        # or inside Blender (numpy is bundled)
    ... [--json out/sanctum-qa.json] [--partial]

Works on any folder of f_####.png (or .jpg). With all 300 frames it also judges flicker and the
loop seam and exits 1 if a criterion fails; with --partial (key frames, previews) it only reports.
All brightness values are display-referred (0..1, as encoded in the files), Rec.709 luma.

Criteria (first version measured in brackets):
  no blackout ........... darkest frame >= 60 % of the mean                 [0.6 %]
  no strobe ............. frame-to-frame mean change <= 0.04, flashes >= 0.10: none   [0.515, 22]
  hierarchy ............. top quarter darker than the middle half on >= 95 % of frames [2 %]
  library readable ...... shelf zone median >= 0.08 and p90-p10 >= 0.08 on >= 95 % of frames
  sculptures not clipped  < 0.5 % of the Michael zone above 0.98; its median within 0.40-0.70
  lasers restrained ..... pixels above 0.85 never more than 6 % of the frame      [18.7 %]
  loop seam ............. RMSE(last -> first) <= 1.5 x the median adjacent RMSE
"""
import glob
import json
import os
import sys

import numpy as np

ZONES = dict(shelf_l=(0.125, 0.182, 0.28, 0.72), shelf_r=(0.818, 0.875, 0.28, 0.72),
             michael=(0.455, 0.545, 0.30, 0.62))                    # x0, x1, y0, y1 (y from the top)


def load(path, width=480):
    """RGB float array (h, w, 3), downscaled to `width` for speed"""
    try:
        from PIL import Image
        im = Image.open(path).convert("RGB")
        im = im.resize((width, max(1, round(im.height * width / im.width))), Image.BILINEAR)
        return np.asarray(im, dtype=np.float32) / 255.0
    except ImportError:
        import bpy
        img = bpy.data.images.load(path, check_existing=False)
        try:
            w, h = img.size
            a = np.empty(w * h * 4, dtype=np.float32)
            img.pixels.foreach_get(a)
            a = a.reshape(h, w, 4)[::-1, :, :3]
            step = max(1, w // width)
            return a[::step, ::step].copy()
        finally:
            bpy.data.images.remove(img)


def luma(rgb):
    return rgb @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)


def crop(a, box):
    h, w = a.shape[:2]
    x0, x1, y0, y1 = box
    return a[int(y0 * h):int(y1 * h), int(x0 * w):int(x1 * w)]


def flashes(m, threshold=0.10):
    """count brightness peaks that rise and fall by at least `threshold` (hysteresis tracker)"""
    peaks, mode, hi, lo, hi_i = [], 0, m[0], m[0], 0
    for i, v in enumerate(m):
        if mode >= 0:
            if v > hi:
                hi, hi_i = v, i
            if hi - v >= threshold:
                peaks.append(hi_i); mode, lo = -1, v
        if mode <= 0:
            if v < lo:
                lo = v
            if v - lo >= threshold:
                mode, hi, hi_i = 1, v, i
    worst = max([sum(1 for p in peaks if s <= p < s + 30) for s in range(len(m))] or [0])
    return len(peaks), worst


def main():
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    partial = "--partial" in a
    out_json = a[a.index("--json") + 1] if "--json" in a else None
    folder = next((x for x in a if not x.startswith("--") and x != out_json), None)
    if not folder:
        sys.exit(__doc__)
    files = sorted(glob.glob(os.path.join(folder, "f_*.png")) + glob.glob(os.path.join(folder, "f_*.jpg")))
    if not files:
        sys.exit("no f_*.png / f_*.jpg in " + folder)
    rows, prev, first, rmse = [], None, None, []
    for path in files:
        rgb = load(path)
        y = luma(rgb)
        h = y.shape[0]
        shelf = np.concatenate([crop(y, ZONES["shelf_l"]).ravel(), crop(y, ZONES["shelf_r"]).ravel()])
        mich = crop(y, ZONES["michael"])
        rows.append(dict(file=os.path.basename(path), mean=float(y.mean()), top=float(y[:h // 4].mean()),
                         mid=float(y[h // 4:3 * h // 4].mean()), shelf_median=float(np.median(shelf)),
                         shelf_contrast=float(np.percentile(shelf, 90) - np.percentile(shelf, 10)),
                         michael_median=float(np.median(mich)), michael_clipped=float((mich > 0.98).mean()),
                         bright=float((y > 0.85).mean())))
        if prev is not None:
            rmse.append(float(np.sqrt(np.mean((rgb - prev) ** 2))))
        first = rgb if first is None else first
        prev = rgb
    m = np.array([r["mean"] for r in rows])
    n = len(rows)
    frac = lambda cond: float(np.mean(cond))
    result = dict(folder=folder, frames=n, mean=float(m.mean()), darkest=float(m.min()),
                  darkest_over_mean=float(m.min() / m.mean()),
                  top_darker_than_mid=frac(np.array([r["top"] < r["mid"] for r in rows])),
                  shelf_readable=frac(np.array([r["shelf_median"] >= 0.08 and r["shelf_contrast"] >= 0.08 for r in rows])),
                  shelf_median=float(np.mean([r["shelf_median"] for r in rows])),
                  michael_median=float(np.mean([r["michael_median"] for r in rows])),
                  michael_clipped_max=float(max(r["michael_clipped"] for r in rows)),
                  bright_max=float(max(r["bright"] for r in rows)))
    checks = dict(no_blackout=result["darkest_over_mean"] >= 0.60,
                  hierarchy=result["top_darker_than_mid"] >= 0.95,
                  library_readable=result["shelf_readable"] >= 0.95,
                  sculptures_not_clipped=result["michael_clipped_max"] < 0.005 and 0.40 <= result["michael_median"] <= 0.70,
                  lasers_restrained=result["bright_max"] <= 0.06)
    full = n == 300 and not partial
    if full:
        steps = np.abs(np.diff(np.concatenate([m, m[:1]])))
        count, worst = flashes(m)
        seam = float(np.sqrt(np.mean((first - prev) ** 2)))
        result.update(max_step=float(steps.max()), flashes=count, flashes_worst_second=worst,
                      seam_rmse=seam, median_adjacent_rmse=float(np.median(rmse)), max_adjacent_rmse=float(max(rmse)))
        checks.update(no_strobe=result["max_step"] <= 0.04 and count == 0,
                      loop_seam=seam <= 1.5 * result["median_adjacent_rmse"] + 1e-4)
    result["checks"] = checks
    result["passed"] = all(checks.values())
    print("frames %d | mean %.3f | darkest %.3f (%.0f %% of mean) | shelf median %.3f | Michael median %.3f | "
          "brightest-pixel share max %.1f %%" % (n, result["mean"], result["darkest"], 100 * result["darkest_over_mean"],
                                               result["shelf_median"], result["michael_median"], 100 * result["bright_max"]))
    if full:
        print("max step %.4f | flashes %d (worst second %d) | seam RMSE %.4f vs median adjacent %.4f"
              % (result["max_step"], result["flashes"], result["flashes_worst_second"], result["seam_rmse"],
                 result["median_adjacent_rmse"]))
    else:
        for r in rows:
            print("  %-12s mean %.3f top %.3f mid %.3f shelf %.3f/%.3f michael %.3f clipped %.2f%% bright %.1f%%"
                  % (r["file"], r["mean"], r["top"], r["mid"], r["shelf_median"], r["shelf_contrast"], r["michael_median"],
                     100 * r["michael_clipped"], 100 * r["bright"]))
    for k, v in checks.items():
        print("  [%s] %s" % ("PASS" if v else "FAIL", k))
    if out_json:
        result["per_frame"] = rows
        with open(out_json, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
    if full and not result["passed"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
