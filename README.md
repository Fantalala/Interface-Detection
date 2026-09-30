# detect_interfaces.py: interfaces of oil-coated bubbles at a free surface

`detect_interfaces.py` finds and measures the two interfaces of an oil-coated air bubble as it bursts at a water free surface. It works on backlit (shadowgraph) high-speed recordings, and it reports both interfaces in every frame:

| Interface | Colour in the videos | What it is |
|---|---|---|
| **inner**: oil / air | magenta | Edge of the air cavity, later of the open crater. |
| **outer**: water / oil | cyan | Edge of the whole compound object. |
| **both**: water / air | magenta with cyan dashes | Stretches with no oil between air and water. Here the two interfaces are the same curve, and the script stores them as identical. |

Each interface is one continuous, ordered, sub-pixel curve. It runs from the free surface on the left, down the wall, around the bottom, and back up to the free surface on the right. Every point is flagged as **measured** (a real edge was found there) or **not measured** (hidden by the meniscus band and extrapolated). After the collapse, the script also traces the oil drop that is left behind.

Current version: **v3** (2026-09-29). See the [version history](#version-history).

![before / after](smooth_overlap_v2_vs_v3.png)

*Left: previous version (v2). Right: current version (v3), with smooth profiles and both curves overlapping on the water/air walls.*

---

## Contents

1. [Quick start](#quick-start)
2. [Requirements](#requirements)
3. [Input data and assumptions](#input-data-and-assumptions)
4. [Outputs](#outputs)
5. [Reading the results in Python](#reading-the-results-in-python)
6. [How it works](#how-it-works)
7. [Measured vs. not measured](#measured-vs-not-measured)
8. [Command-line options](#command-line-options)
9. [Tuning and troubleshooting](#tuning-and-troubleshooting)
10. [Accuracy and validation](#accuracy-and-validation)
11. [Results on the 10 g/L SDS / 3 cSt oil recordings](#results-on-the-10-gl-sds--3-cst-oil-recordings)
12. [Known limitations](#known-limitations)
13. [Version history](#version-history)

---

## Quick start

```bash
# whole video, default settings
python detect_interfaces.py movie.avi --out results

# with spatial calibration (metrics in mm, contours stay in px)
python detect_interfaces.py movie.avi --out results --px-per-mm 50

# only the collapse, frames 0..59
python detect_interfaces.py movie.avi --out results --stop 60

# multi-page TIFF stack (Photron / Phantom export)
python detect_interfaces.py stack.tif --out results --fps 10000

# look at what the detector sees in a few frames, then exit
python detect_interfaces.py movie.avi --out results --debug 0 20 30

# a single image, with a separate background image
python detect_interfaces.py single.png --bg background.png --out results
```

A run prints what it detected. The free-surface row and the meniscus-band limits are worth a quick check:

```text
Loading movie.avi ...
  236 frames, 1024x672
  background: patched leftover object(s) in x=326-902, y=130-531 (7.8% of image)
  free surface at y = 289 px (auto)
  free-surface zone: y = 289 .. 423 px
  frame 0: outer area 94286, inner area 83792 px^2
  ...
Done.
```

**Speed:** roughly 0.5–1 s per 1024×672 frame on one CPU core, so a 300-frame video takes about 5 min. Several videos can run in parallel.

**Memory:** the whole sequence is loaded as float32, which is about 0.8 GB for 300 frames at 1024×672.

---

## Requirements

- **Python** 3.9 or newer.
- **Required packages:** `numpy`, `scipy`, `opencv-python`, `scikit-image`.
- **Optional packages:**
  - `matplotlib`, for the `_profiles.png` plot. Without it the plot is skipped.
  - `tifffile`, for reading large or 16-bit TIFF stacks. Without it, OpenCV's reader is used.

```bash
pip install numpy scipy opencv-python scikit-image matplotlib tifffile
```

The script is a single file with no other dependencies.

---

## Input data and assumptions

- **Formats**
  - Videos: `.avi`, `.mp4`, `.mov`, `.mkv`, `.wmv`, `.m4v`, `.mpg`.
  - Multi-page TIFF stacks.
  - Single images: `.tif`, `.png`, `.jpg`, …
  - Colour input is converted to grayscale. 12- and 16-bit data are rescaled.
- **Imaging:** backlit shadowgraphy.
  - Water is bright or gray.
  - The air cavity is black.
  - The oil shell is a gray crescent with a dark rim.
  - Inside the dark meniscus band just below the free surface, the oil can instead appear *brighter* than water, because the shell acts as a lens. The script handles this.
- **Geometry**
  - The free surface is roughly horizontal, somewhere in the upper 5–60 % of the image.
  - The bubble or crater is below it.
  - The object is roughly **axisymmetric** about a vertical axis, so every horizontal cut through it is one interval. The segmentation relies on this.
- **Background**
  - By default the background is the median of the **last 15 frames**, when the bubble has gone.
  - If something is still there, such as the leftover drop, it is detected and patched automatically; the log line `background: patched leftover object(s) …` reports this.
  - Other options: `--bg-mode first` (use the first frames), `--bg background.png` (a separate image), or `--bg-mode margins` (estimate the background row by row from the image margins; this is used automatically for single images).
- **Frame rate:** `--fps` sets the time axis, `time_ms = frame / fps × 1000`. The default is 10 000.
- **Sequences:** the script uses information from the previous frame, so run it on the frames **in order**, starting before or at the burst. See [How it works](#how-it-works).

Nothing above the **cut line** is analysed. The cut line is the free surface plus `--surface-margin` (6 px); it is the orange line in the videos.

---

## Outputs

For an input `NAME.avi`, the output directory contains:

| File | Content |
|---|---|
| `NAME_annotated.mp4` | Every frame with both interfaces drawn. |
| `NAME_metrics.csv` | One row per frame: areas, radii, positions, film thickness, quality flags. |
| `NAME_contours.npz` | All curves, flags and wall profiles of every frame, in pixels. |
| `NAME_profiles.png` | All interface curves of the collapse overlaid, coloured by time. |
| `NAME_debug_XXXX.png` | Only with `--debug`: diagnostic panels. |
| `NAME_XXXXX.png` | Only with `--save-frames`: each annotated frame as a PNG. |

### Annotated video

- **Magenta:** oil/air interface.
- **Cyan:** water/oil interface.
- **Magenta with cyan dashes:** water/air. There is no oil here, and both interfaces are this curve.
- **Thick line:** measured. **Thin, lighter line:** not measured (extrapolated).
- **Orange horizontal line:** the cut line (free surface + margin).
- A frame label shows the frame index and time.
- Playback is at `--video-fps` (default 30).

### `NAME_metrics.csv`

Lengths are in px, or in mm if `--px-per-mm` is given; areas are in px² or mm². **NaN means the interface does not exist in that frame**, for example the inner interface after the cavity has closed.

| Column | Meaning |
|---|---|
| `frame`, `time_ms` | Frame index and time. |
| `outer_area`, `inner_area` | Area enclosed by the curve and the cut line: the whole object, and the air cavity/crater. Areas are projected, i.e. 2-D cross-sections below the cut line. |
| `outer_eq_radius`, `inner_eq_radius` | √(area / π). |
| `outer_cx`, `outer_cy`, `inner_cx`, `inner_cy` | Centroid of the enclosed region. |
| `outer_bottom_y`, `inner_bottom_y` | Lowest point of the curve (sub-pixel; y increases downward). |
| `outer_width`, `inner_width` | Horizontal extent of the curve. |
| `oil_thickness_bottom` | Vertical oil-film thickness at the bottom: the outer curve's lowest crossing of the vertical line x = `inner_cx`, minus the inner curve's lowest crossing of the same line. |
| `oil_area` | `outer_area − inner_area`: the projected oil area. |
| `inner_measured_frac`, `outer_measured_frac` | Fraction of curve points that are measured. |
| `water_air_contact_frac` | Fraction of the outer curve that is water/air, i.e. overlapping the inner curve. |
| `outer_top_cut` | 1 = no cavity, and the drop outline was cut flat where the meniscus band hides its neck. The drop is still hanging from the surface, and only the part below the band is measured. |
| `outer_top_in_band` | 1 = no cavity, and the drop outline closes inside the meniscus band. The drop may still be attached through a hidden neck; treat its area and centroid as "visible part". |

### `NAME_contours.npz`

All coordinates are in **pixels**, even with `--px-per-mm`. x is the image column (increasing to the right) and y is the image row (increasing downward). `XXXXX` is the frame index with 5 digits, e.g. `00021`. A key is missing when the interface does not exist in that frame.

| Key | Shape / type | Meaning |
|---|---|---|
| `inner_curve_XXXXX` | (N, 2) float32 | Oil/air interface as one ordered sub-pixel curve (x, y): free surface (left) → bottom → free surface (right). |
| `outer_curve_XXXXX` | (M, 2) float32 | Water/oil interface, same ordering. Where there is no oil it runs *on* the inner curve. |
| `inner_measured_XXXXX` | (N,) bool | Per point: True = measured, False = extrapolated or no clear edge. |
| `outer_measured_XXXXX` | (M,) bool | The same for the outer curve. |
| `outer_contact_XXXXX` | (M,) bool | Per outer point: True = water/air contact. These points are copied exactly from the inner curve, so they lie on it (distance 0). |
| `inner_strength_XXXXX`, `outer_strength_XXXXX` | float32 | Edge strength per point: derivative of the flat-fielded image across the curve (1/px). Larger means a sharper edge. |
| `inner_prof_XXXXX`, `outer_prof_XXXXX` | (K, 3) | Per image row y: (y, x_left, x_right), the leftmost and rightmost crossings of the curve with that row (sub-pixel). Use this for r(y) = (x_right − x_left) / 2. |
| `inner_XXXXX`, `outer_XXXXX` | (L, 2) int32 | Closed pixel contour of the *segmentation mask* before sub-pixel refinement. Mostly useful for debugging. |
| `surface_y`, `cut_y`, `zone_bottom` | scalar | Free-surface row, cut row (nothing above it is analysed), and lower edge of the meniscus band. |

### `NAME_profiles.png`

Two panels: the oil/air and water/oil curves of **every frame that has a cavity**, overlaid on the first frame and coloured by time. Bold segments are measured; thin segments are extrapolated. This gives a quick overview of the collapse and of capillary waves on the walls.

### Debug panels (`--debug i j k …`)

For each listed frame, a 2×2 panel:

- top left: the annotated frame;
- top right: the flat-fielded ratio image with the curves;
- bottom left: the masks;
- bottom right: the masks overlaid on the ratio image.

Debug mode processes each frame **on its own**, without the frame-to-frame information of a full run. Late-collapse frames can therefore look different from the full run. Use a full run (optionally with `--save-frames`) to see exactly what the video shows.

---

## Reading the results in Python

```python
import numpy as np
import pandas as pd

d = np.load("results/NAME_contours.npz")
key = "00021"                                   # frame 21

# both interfaces as sub-pixel curves
x_in,  y_in  = d[f"inner_curve_{key}"].T        # oil / air
x_out, y_out = d[f"outer_curve_{key}"].T        # water / oil (water / air where no oil)
ok_in   = d[f"inner_measured_{key}"]            # False = extrapolated
contact = d[f"outer_contact_{key}"]             # True = water / air, lies on the inner curve

# measured points only
xm, ym = x_in[ok_in], y_in[ok_in]

# local cavity radius r(y) from the per-row wall positions
y, xl, xr = d[f"inner_prof_{key}"].T
r = (xr - xl) / 2

# triple points (water / oil / air): where the outer curve joins or leaves the inner curve
j = np.flatnonzero(np.diff(contact.astype(int)))
triple_points = np.c_[x_out[j], y_out[j]]

# frames that have a cavity
frames = sorted(int(k[-5:]) for k in d.files if k.startswith("inner_curve_"))

# per-frame metrics
m = pd.read_csv("results/NAME_metrics.csv")
cavity = m[m.inner_area.notna()]
print(cavity[["time_ms", "inner_bottom_y", "oil_thickness_bottom", "water_air_contact_frac"]])

# the free surface / cut line / meniscus band used for this video
print(int(d["surface_y"]), int(d["cut_y"]), int(d["zone_bottom"]))
```

Overlaying the curves on a raw frame:

```python
import cv2, matplotlib.pyplot as plt
cap = cv2.VideoCapture("movie.avi"); cap.set(cv2.CAP_PROP_POS_FRAMES, 21)
ok, img = cap.read()
plt.imshow(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), cmap="gray")
plt.plot(x_out, y_out, "c-", lw=1)
plt.plot(x_in, y_in, "m-", lw=1)
plt.plot(x_in[~ok_in], y_in[~ok_in], "w.", ms=1)      # extrapolated points
plt.show()
```

---

## How it works

### Per frame

1. **Flat-fielding.**
   - The frame is divided by the background: `ratio = frame / background`. Water becomes ≈ 1, oil 0.4–0.8, and air < 0.3.
   - Every row is then normalised by the image margins. This removes brightness changes that are uniform along a row, e.g. from free-surface motion.
2. **Free surface and meniscus band.**
   - The free surface is the steepest bright-to-dark step of the background's row profile.
   - The *meniscus band* is the dark, striped zone below it, down to where the background has recovered towards the water level. Its horizontal stripes are the main difficulty for edge detection.
3. **Reliable lower object.** Below the band, the object is simply `ratio < 1 − t_out`.
4. **Air cavity (inner interface).**
   - The cavity is segmented by a marker-controlled **watershed** on the gradient magnitude:
     - "surely air" markers where `ratio < t_air`;
     - "surely not air" markers where `ratio > t_bright`.
   - The boundary therefore lies on the gradient ridge, not at a fixed threshold.
   - Several fixes then follow:
     - bright lensing spots inside the cavity are not used as "not air" markers;
     - small round **surface bubbles** (circle detection, tracked across frames) are excluded;
     - crater pieces cut off by a light stripe are merged back;
     - bays that a stripe cuts into a sloping wall are bridged along the slope;
     - thin dark streaks under the surface are rejected.
   - Every row is filled, because of axisymmetry.
5. **Walls near the surface.**
   - In the top `--top-rows` rows the stripes can make the wall step sideways. Steep walls are therefore re-traced upward from a clean anchor below by a 2nd-order dynamic-programming wall tracker, using the horizontal gradient only.
   - The tracker is bounded by the first bright ridge met going outward from the crater, so it cannot jump onto the oil's outer rim.
   - The shallow rims of a late, wide crater are fitted as one smooth curve instead: crater bottom → quadratic rim → free surface, with the anchor and shape searched for the best edge evidence.
   - If a wall is closed off below the surface, it is traced or extrapolated up to the surface.
6. **Whole object (outer interface).**
   - The lower object is traced upward through the band row by row, using the **local** water level just outside it.
   - A candidate is accepted if it is darker than water (the rim) or, inside the band, brighter than water (the lens-like crescent).
   - Where the oil has ended, the outline is the air wall itself (water/air contact).
7. **Sub-pixel refinement.**
   - Each contour is refined along its normals by dynamic programming (globally optimal and smooth) to the maximum of the directional derivative, with the correct polarity: dark inside, bright outside.
   - The oil/air edge may move outward only through a monotonically brightening profile, so it never crosses onto the water/oil interface.
   - The water/oil edge may move inward only down the darkening ramp into its rim.
8. **Smoothing.**
   - Loops and narrow folds are removed.
   - The curves are smoothed along their arc length (`--smooth`, 4 px). Flat stretches inside the band get stronger smoothing (`--smooth-band`, 10 px).
   - Unmeasured ends are continued smoothly up to the free surface.
9. **Water/air contact.**
   - Outer points closer than `--contact-d` (3 px) to the inner curve are water/air contact. So are unmeasured end stretches that start at the inner curve.
   - These stretches are replaced by the matching piece of the inner curve, so both curves are identical there.
   - The corners where they separate are the triple points.
10. **Metrics.** Areas, centroids and so on are computed from the final sub-pixel curves.

### Across frames (videos and stacks)

The script remembers what it found in the previous frame, and uses it in these ways:

- **Crater bottom in the band.** The bottom is only gray and striped there. The previous cavity, eroded by `--prior-erode` px, seeds "surely air". The crater bottom may sink by at most `--max-sink` px per frame inside the band, because it only rises or widens while it collapses. A new air region must overlap the previous one.
- **Surface bubbles** are tracked. A bubble missed by the detector is looked for again near its last position.
- **End of the cavity.** The cavity collapses only once. Tracking stops for good when the crater has relaxed into the free surface. That means any of these:
  - no black left in it (`--min-core-frac`);
  - flat (`--min-relief`);
  - spread into the image margins;
  - shallower than `--min-depth-track`;
  - mostly extrapolated for 2 frames.
  From then on the inner metrics are NaN, and only the leftover drop is traced.
- **Drop after the collapse.**
  - While the drop hangs from the surface, its neck inside the band is not extrapolated; the outline ends with a flat, not-measured top.
  - Once its top is visible it is traced in polar coordinates, preferring the outline most similar to the previous frame's.

Because of this, **process a sequence in order from before or at the burst**. With `--start` in the middle of a collapse, the first frames have no history and the band region can be less reliable.

---

## Measured vs. not measured

A curve point is **measured** when there is a clear edge there: an edge strength of at least `--g-meas` (0.03 per px) across the curve, and it is not in a row where the wall had to be bridged or extrapolated. Typical places where points are **not measured**:

- the top of the walls inside the meniscus band, where a stripe hides the edge;
- the short piece of wall between the last visible edge and the free surface;
- rows behind a surface bubble sitting on the wall;
- the flat top of a drop whose neck is hidden in the band.

For quantitative work, use `*_measured_*` to restrict fits to measured points. `inner_measured_frac` and `outer_measured_frac` in the CSV give a quick per-frame quality indicator.

---

## Command-line options

`python detect_interfaces.py --help` prints all of them. The defaults are tuned for the 1024×672, 10 000 fps recordings described [below](#results-on-the-10-gl-sds--3-cst-oil-recordings).

### Input, frames, output

| Option | Default | Meaning |
|---|---|---|
| `input` | — | Video, TIFF stack or image. |
| `--out` | `interfaces_out` | Output directory. |
| `--start`, `--stop`, `--step` | 0, end, 1 | Frames to process. The background is always built from the whole sequence. |
| `--fps` | 10000 | Recording frame rate, for `time_ms`. |
| `--px-per-mm` | none | Spatial calibration: metrics in mm (contours stay in px). |
| `--video-fps` | 30 | Playback rate of the annotated video. |
| `--save-frames` | off | Also write every annotated frame as a PNG. |
| `--debug i j …` | off | Write debug panels for these frames and exit. |

### Background and free surface

| Option | Default | Meaning |
|---|---|---|
| `--bg FILE` | none | Background image without the bubble. |
| `--bg-mode` | `last` | Background from the `last` or `first` N frames, or from the image `margins`. |
| `--bg-n` | 15 | N frames for the background. |
| `--no-bg-clean` | off | Do not patch objects left in the background frames. |
| `--no-row-norm` | off | Disable row-wise normalisation by the image margins. |
| `--margin-frac` | 0.10 | Width fraction of each side margin used as the reference. |
| `--surface-y` | auto | Row of the free surface. Set it if auto-detection is wrong. |
| `--surface-margin` | 6 | Rows below the free surface that are ignored; the cut line is `surface_y + this`. |
| `--surface-zone` | auto | Height of the meniscus band (px). |
| `--seed X Y` | image centre | A pixel inside the bubble, if the object is not near the centre. |

### Segmentation thresholds (ratio = frame / background; water ≈ 1)

| Option | Default | Meaning |
|---|---|---|
| `--t-air` | 0.25 | Ratio below this = surely air (watershed marker). |
| `--t-bright` | 0.55 | Ratio above this = surely not air (watershed marker). |
| `--t-air-hi` | 0.55 | A traced cavity wall needs a ratio below this just inside it. |
| `--t-out` | 0.15 | Darker than (1 − t_out) × local water = not water (the object's rim). |
| `--t-lens` | 0.20 | Inside the band, brighter than (1 + t_lens) × local water = oil too (lens effect). |
| `--air-reach` | 6 | Below the band, the cavity edge lies within this many px of "surely air" pixels. This keeps gray oil lobes out of the cavity. |
| `--min-depth-air` | 30 | A new air region must reach at least this far below the cut line; anything shallower is surface shadow. |
| `--min-area`, `--min-area-air` | 300, 150 | Minimum component areas (px²). |
| `--blur` | 1.5 | Gaussian σ for segmentation (px). |
| `--edge-sigma` | 1.0 | Gaussian σ for sub-pixel edge localisation (px). |
| `--open-r`, `--close-r`, `--open-r-air` | 2, 4, 1 | Morphology radii. |
| `--notch` | 9 | Horizontal slits up to this many rows tall are closed. |
| `--bay` | 41 | Maximum height (rows) of bays in a wall that are bridged inside the band; 0 = off. |
| `--no-satellites` | off | Do not look for small surface bubbles. |

### Walls near the surface

| Option | Default | Meaning |
|---|---|---|
| `--top-rows` | 45 | The walls in this many rows below the surface are re-traced as smooth continuations of the wall below. |
| `--dip-tol-wall` | 0.10 | A re-traced wall stops at the first bright ridge (a drop of more than this after a rise) met going outward from the crater. |
| `--shallow-slope` | 1.0 | Walls flatter than this (dy/dx) get a smooth parametric rim instead of a row-wise trace. |
| `--rim-keep` | 0.6 | The parametric rim replaces the segmented one if it has at least this fraction of its edge evidence. |

### Sub-pixel refinement, smoothing, contact

| Option | Default | Meaning |
|---|---|---|
| `--win-in-air`, `--win-out-air` | 4, 16 | px the oil/air edge may move inward or outward during refinement. It moves outward only through a brightening profile. |
| `--dip-tol` | 0.05 | Maximum darkening allowed on the way outward (oil/air). |
| `--win-in-out`, `--win-out-out` | 8, 3 | px the water/oil edge may move inward or outward. |
| `--rise-tol` | 0.05 | Maximum brightening allowed on the way inward (water/oil). |
| `--lam` | 0.06 | Stiffness of the refinement (penalty per px change of offset between neighbouring points). |
| `--smooth` | 4 | Gaussian smoothing of the final curves along their arc length (px); 0 = off. |
| `--smooth-band` | 10 | Stronger smoothing of flat stretches inside the meniscus band (px); 0 = off. |
| `--contact-d` | 3 | Closer than this (px) to the oil/air curve means no oil: water/air contact, and the curves are merged. |
| `--g-meas` | 0.03 | Minimum edge strength (1/px) for a point to count as measured. |

### Frame-to-frame tracking

| Option | Default | Meaning |
|---|---|---|
| `--prior-erode` | 12 | Inside the band, the previous cavity eroded by this many px seeds "surely air"; 0 = off. It is eroded more while the bottom rises fast. |
| `--t-prior` | 0.45 | The previous cavity seeds air only where the ratio is below this. |
| `--max-sink` | 2 | px per frame that the crater bottom may move down inside the band; −1 = off. |
| `--bottom-width` | 81 | Pockets and notches in the crater bottom inside the band that are narrower than this (px) are removed. |
| `--min-depth-track` | 15 | A tracked crater shallower than this ends the tracking. |
| `--min-relief` | 12 | A tracked crater must be at least this much deeper in the middle than at its rim; if it is flatter, tracking ends. |
| `--min-core-frac` | 0.05 | An air region needs at least this fraction of "surely air" pixels; if it has fewer, tracking ends. |
| `--no-drop-top` | off | Do not trace the top of a detached drop inside the band. |

---

## Tuning and troubleshooting

| Symptom | What to do |
|---|---|
| The orange cut line is not at the free surface. | Set `--surface-y ROW`, e.g. read from `--debug 0`. If the band limits look wrong, set `--surface-zone PX` as well. |
| The background log says a large area was patched, or the background still contains the bubble. | Use `--bg-mode first` if the first frames are clean, or give `--bg background.png`. |
| Magenta leaks into gray oil next to the cavity. | Lower `--t-bright` (e.g. 0.5) or `--air-reach` (e.g. 4). |
| Magenta sits inside the black cavity. | Raise `--t-air` slightly (e.g. 0.3). Check with `--debug` that the ratio image of the cavity is < 0.3. |
| Cyan misses a faint oil rim. | Lower `--t-out` (e.g. 0.10). |
| Curves too smooth or too wiggly. | Change `--smooth` (px), `--smooth-band` and `--lam`. |
| Tracking ends too early or too late. | Change `--min-relief`, `--min-core-frac` and `--min-depth-track`. |
| The crater bottom lags behind the image during a fast rise. | Lower `--prior-erode` (less memory) or raise `--max-sink`. |
| Different magnification or resolution. | Scale the pixel parameters: `--top-rows`, `--bay`, `--bottom-width`, `--min-depth-*`, `--min-area*`, `--smooth*`. Thresholds on the ratio need no change. |

A good first check on new data is to run `--debug` on a few frames (before the burst, mid-collapse, late collapse), then do a full run and step through `_annotated.mp4`.

---

## Accuracy and validation

These checks were run on the three distinct recordings below (frames 0–27, every 3rd frame, about 35 000 measured curve points). The offset is the distance from each measured curve point to the strongest edge along its normal.

| | median offset | 90th percentile | within 1.5 px |
|---|---|---|---|
| oil/air, below the meniscus band | 0.25 px | 0.5 px | 98 % |
| oil/air, inside the band | 0.25 px | 1.75 px | 89 % |
| water/oil, below the band | 0.25 px | 1.25 px | 91 % |

Other checks:

- **Smoothness** (RMS deviation from a 6 px-smoothed copy of the curve, 60 frames):
  - oil/air: 0.55 px in v2 → 0.28 px in v3;
  - water/oil: 0.53 px → 0.36 px.
  - Sharp turns (99th percentile of the turning angle per 3 px) are about 4 times rarer.
- **Overlap:** every outer point flagged as water/air contact lies at **0.000 px** from the inner curve, in every frame of all videos.
- **Visual review:** a separate reviewer compared the annotated collapse frames of all three videos with the raw frames, in several rounds, with zoomed checks of the problem areas.

---

## Results on the 10 g/L SDS / 3 cSt oil recordings

The recordings are Camera 2, 10 000 fps, 1024×672. S0001_2 is a byte-identical copy of S0001_1.

| Recording | Frames | Free surface y | Band until y | Cavity tracked (frames) | Median measured (oil/air) | Median water/air fraction |
|---|---|---|---|---|---|---|
| C001H001S0001_1 | 300 | 263 | 416 | 0–57 | 0.84 | 0.24 |
| C001H001S0002_1 | 226 | 285 | 418 | 0–78 | 0.93 | 0.57 |
| C001H001S0005_2 | 236 | 289 | 423 | 0–64 | 0.92 | 0.50 |

---

## Known limitations

- **Drop still attached through a hidden neck** (S0001 frames 60–180). The outline closes where the neck enters the meniscus band, so the area and centroid describe only the visible part. These frames are flagged `outer_top_in_band` / `outer_top_cut`.
- **A drop lying entirely inside the meniscus band** is not traced (S0001 after about frame 185; 106 frames without an outer curve).
- **Very shallow late crater** (S0001 frames 40–57, S0002 frames 53–55). The band's stripes are ambiguous here, and a few smooth S-shaped rises of 5–12 px remain in the rim.
- **Extrapolated ends at the surface.** Where both curves are extrapolated right below the surface, they can occasionally run up to the cut line separately (e.g. S0001 frame 32, left).
- **Thin oil lobes.** When an oil lobe beside the cavity is very thin (S0002 frames 19–20, right), part of it can be counted as air.
- **Projection.** All quantities are projected, 2-D quantities. Volumes need an axisymmetric reconstruction from `*_prof_*`.
- **Nothing above the cut line** (free surface + 6 px) is analysed.

---

## Version history

### v3 (2026-09-29): smooth profiles, water/air overlap

- Final curves are smoothed along their arc length; stronger smoothing is applied to flat stretches inside the meniscus band; loops and folds are removed; unmeasured ends are continued smoothly to the surface.
- Walls near the surface are re-traced by DP on the horizontal gradient, bounded by the first bright ridge. Shallow rims are fitted as one smooth parametric curve. Together these remove the L-shaped shelves, boxes, hooks and stripe staircases.
- Surface bubbles are tracked from frame to frame and bridged.
- Water/air contact: the outer curve is copied exactly from the inner curve wherever there is no oil. It is drawn as magenta with cyan dashes and flagged as `outer_contact_XXXXX` and `water_air_contact_frac`.
- The crater sink limit applies only to the crater bottom, not to its walls.

### v2

- Edges are placed at the gradient maximum instead of a fixed threshold. v1's oil/air curve sat 2–8 px inside the cavity.
- The cavity is segmented by a gradient watershed, and both interfaces are refined by dynamic programming along their normals.
- Handling of the meniscus band: wall tracking, crater pieces merged back, surface bubbles excluded, oil lobes kept out of the air.
- Late collapse: the curve follows the crater bottom resting on the drop, and meets the drop rims at the triple points.
- Frame-to-frame tracking: prior-seeded crater bottom, sink limit, and a clean end of the cavity (NaN metrics afterwards).
- The leftover drop is traced; detached drop tops are traced in polar coordinates.

### v1

- Fixed thresholds on the flat-fielded image, row filling, and row-wise edge tracking in the band.# detect_interfaces.py: interfaces of oil-coated bubbles at a free surface

`detect_interfaces.py` finds and measures the two interfaces of an oil-coated air bubble as it bursts at a water free surface. It works on backlit (shadowgraph) high-speed recordings, and it reports both interfaces in every frame:

| Interface | Colour in the videos | What it is |
|---|---|---|
| **inner**: oil / air | magenta | Edge of the air cavity, later of the open crater. |
| **outer**: water / oil | cyan | Edge of the whole compound object. |
| **both**: water / air | magenta with cyan dashes | Stretches with no oil between air and water. Here the two interfaces are the same curve, and the script stores them as identical. |

Each interface is one continuous, ordered, sub-pixel curve. It runs from the free surface on the left, down the wall, around the bottom, and back up to the free surface on the right. Every point is flagged as **measured** (a real edge was found there) or **not measured** (hidden by the meniscus band and extrapolated). After the collapse, the script also traces the oil drop that is left behind.

Current version: **v3** (2026-09-29). See the [version history](#version-history).

![before / after](smooth_overlap_v2_vs_v3.png)

*Left: previous version (v2). Right: current version (v3), with smooth profiles and both curves overlapping on the water/air walls.*

---

## Contents

1. [Quick start](#quick-start)
2. [Requirements](#requirements)
3. [Input data and assumptions](#input-data-and-assumptions)
4. [Outputs](#outputs)
5. [Reading the results in Python](#reading-the-results-in-python)
6. [How it works](#how-it-works)
7. [Measured vs. not measured](#measured-vs-not-measured)
8. [Command-line options](#command-line-options)
9. [Tuning and troubleshooting](#tuning-and-troubleshooting)
10. [Accuracy and validation](#accuracy-and-validation)
11. [Results on the 10 g/L SDS / 3 cSt oil recordings](#results-on-the-10-gl-sds--3-cst-oil-recordings)
12. [Known limitations](#known-limitations)
13. [Version history](#version-history)

---

## Quick start

```bash
# whole video, default settings
python detect_interfaces.py movie.avi --out results

# with spatial calibration (metrics in mm, contours stay in px)
python detect_interfaces.py movie.avi --out results --px-per-mm 50

# only the collapse, frames 0..59
python detect_interfaces.py movie.avi --out results --stop 60

# multi-page TIFF stack (Photron / Phantom export)
python detect_interfaces.py stack.tif --out results --fps 10000

# look at what the detector sees in a few frames, then exit
python detect_interfaces.py movie.avi --out results --debug 0 20 30

# a single image, with a separate background image
python detect_interfaces.py single.png --bg background.png --out results
```

A run prints what it detected. The free-surface row and the meniscus-band limits are worth a quick check:

```text
Loading movie.avi ...
  236 frames, 1024x672
  background: patched leftover object(s) in x=326-902, y=130-531 (7.8% of image)
  free surface at y = 289 px (auto)
  free-surface zone: y = 289 .. 423 px
  frame 0: outer area 94286, inner area 83792 px^2
  ...
Done.
```

**Speed:** roughly 0.5–1 s per 1024×672 frame on one CPU core, so a 300-frame video takes about 5 min. Several videos can run in parallel.

**Memory:** the whole sequence is loaded as float32, which is about 0.8 GB for 300 frames at 1024×672.

---

## Requirements

- **Python** 3.9 or newer.
- **Required packages:** `numpy`, `scipy`, `opencv-python`, `scikit-image`.
- **Optional packages:**
  - `matplotlib`, for the `_profiles.png` plot. Without it the plot is skipped.
  - `tifffile`, for reading large or 16-bit TIFF stacks. Without it, OpenCV's reader is used.

```bash
pip install numpy scipy opencv-python scikit-image matplotlib tifffile
```

The script is a single file with no other dependencies.

---

## Input data and assumptions

- **Formats**
  - Videos: `.avi`, `.mp4`, `.mov`, `.mkv`, `.wmv`, `.m4v`, `.mpg`.
  - Multi-page TIFF stacks.
  - Single images: `.tif`, `.png`, `.jpg`, …
  - Colour input is converted to grayscale. 12- and 16-bit data are rescaled.
- **Imaging:** backlit shadowgraphy.
  - Water is bright or gray.
  - The air cavity is black.
  - The oil shell is a gray crescent with a dark rim.
  - Inside the dark meniscus band just below the free surface, the oil can instead appear *brighter* than water, because the shell acts as a lens. The script handles this.
- **Geometry**
  - The free surface is roughly horizontal, somewhere in the upper 5–60 % of the image.
  - The bubble or crater is below it.
  - The object is roughly **axisymmetric** about a vertical axis, so every horizontal cut through it is one interval. The segmentation relies on this.
- **Background**
  - By default the background is the median of the **last 15 frames**, when the bubble has gone.
  - If something is still there, such as the leftover drop, it is detected and patched automatically; the log line `background: patched leftover object(s) …` reports this.
  - Other options: `--bg-mode first` (use the first frames), `--bg background.png` (a separate image), or `--bg-mode margins` (estimate the background row by row from the image margins; this is used automatically for single images).
- **Frame rate:** `--fps` sets the time axis, `time_ms = frame / fps × 1000`. The default is 10 000.
- **Sequences:** the script uses information from the previous frame, so run it on the frames **in order**, starting before or at the burst. See [How it works](#how-it-works).

Nothing above the **cut line** is analysed. The cut line is the free surface plus `--surface-margin` (6 px); it is the orange line in the videos.

---

## Outputs

For an input `NAME.avi`, the output directory contains:

| File | Content |
|---|---|
| `NAME_annotated.mp4` | Every frame with both interfaces drawn. |
| `NAME_metrics.csv` | One row per frame: areas, radii, positions, film thickness, quality flags. |
| `NAME_contours.npz` | All curves, flags and wall profiles of every frame, in pixels. |
| `NAME_profiles.png` | All interface curves of the collapse overlaid, coloured by time. |
| `NAME_debug_XXXX.png` | Only with `--debug`: diagnostic panels. |
| `NAME_XXXXX.png` | Only with `--save-frames`: each annotated frame as a PNG. |

### Annotated video

- **Magenta:** oil/air interface.
- **Cyan:** water/oil interface.
- **Magenta with cyan dashes:** water/air. There is no oil here, and both interfaces are this curve.
- **Thick line:** measured. **Thin, lighter line:** not measured (extrapolated).
- **Orange horizontal line:** the cut line (free surface + margin).
- A frame label shows the frame index and time.
- Playback is at `--video-fps` (default 30).

### `NAME_metrics.csv`

Lengths are in px, or in mm if `--px-per-mm` is given; areas are in px² or mm². **NaN means the interface does not exist in that frame**, for example the inner interface after the cavity has closed.

| Column | Meaning |
|---|---|
| `frame`, `time_ms` | Frame index and time. |
| `outer_area`, `inner_area` | Area enclosed by the curve and the cut line: the whole object, and the air cavity/crater. Areas are projected, i.e. 2-D cross-sections below the cut line. |
| `outer_eq_radius`, `inner_eq_radius` | √(area / π). |
| `outer_cx`, `outer_cy`, `inner_cx`, `inner_cy` | Centroid of the enclosed region. |
| `outer_bottom_y`, `inner_bottom_y` | Lowest point of the curve (sub-pixel; y increases downward). |
| `outer_width`, `inner_width` | Horizontal extent of the curve. |
| `oil_thickness_bottom` | Vertical oil-film thickness at the bottom: the outer curve's lowest crossing of the vertical line x = `inner_cx`, minus the inner curve's lowest crossing of the same line. |
| `oil_area` | `outer_area − inner_area`: the projected oil area. |
| `inner_measured_frac`, `outer_measured_frac` | Fraction of curve points that are measured. |
| `water_air_contact_frac` | Fraction of the outer curve that is water/air, i.e. overlapping the inner curve. |
| `outer_top_cut` | 1 = no cavity, and the drop outline was cut flat where the meniscus band hides its neck. The drop is still hanging from the surface, and only the part below the band is measured. |
| `outer_top_in_band` | 1 = no cavity, and the drop outline closes inside the meniscus band. The drop may still be attached through a hidden neck; treat its area and centroid as "visible part". |

### `NAME_contours.npz`

All coordinates are in **pixels**, even with `--px-per-mm`. x is the image column (increasing to the right) and y is the image row (increasing downward). `XXXXX` is the frame index with 5 digits, e.g. `00021`. A key is missing when the interface does not exist in that frame.

| Key | Shape / type | Meaning |
|---|---|---|
| `inner_curve_XXXXX` | (N, 2) float32 | Oil/air interface as one ordered sub-pixel curve (x, y): free surface (left) → bottom → free surface (right). |
| `outer_curve_XXXXX` | (M, 2) float32 | Water/oil interface, same ordering. Where there is no oil it runs *on* the inner curve. |
| `inner_measured_XXXXX` | (N,) bool | Per point: True = measured, False = extrapolated or no clear edge. |
| `outer_measured_XXXXX` | (M,) bool | The same for the outer curve. |
| `outer_contact_XXXXX` | (M,) bool | Per outer point: True = water/air contact. These points are copied exactly from the inner curve, so they lie on it (distance 0). |
| `inner_strength_XXXXX`, `outer_strength_XXXXX` | float32 | Edge strength per point: derivative of the flat-fielded image across the curve (1/px). Larger means a sharper edge. |
| `inner_prof_XXXXX`, `outer_prof_XXXXX` | (K, 3) | Per image row y: (y, x_left, x_right), the leftmost and rightmost crossings of the curve with that row (sub-pixel). Use this for r(y) = (x_right − x_left) / 2. |
| `inner_XXXXX`, `outer_XXXXX` | (L, 2) int32 | Closed pixel contour of the *segmentation mask* before sub-pixel refinement. Mostly useful for debugging. |
| `surface_y`, `cut_y`, `zone_bottom` | scalar | Free-surface row, cut row (nothing above it is analysed), and lower edge of the meniscus band. |

### `NAME_profiles.png`

Two panels: the oil/air and water/oil curves of **every frame that has a cavity**, overlaid on the first frame and coloured by time. Bold segments are measured; thin segments are extrapolated. This gives a quick overview of the collapse and of capillary waves on the walls.

### Debug panels (`--debug i j k …`)

For each listed frame, a 2×2 panel:

- top left: the annotated frame;
- top right: the flat-fielded ratio image with the curves;
- bottom left: the masks;
- bottom right: the masks overlaid on the ratio image.

Debug mode processes each frame **on its own**, without the frame-to-frame information of a full run. Late-collapse frames can therefore look different from the full run. Use a full run (optionally with `--save-frames`) to see exactly what the video shows.

---

## Reading the results in Python

```python
import numpy as np
import pandas as pd

d = np.load("results/NAME_contours.npz")
key = "00021"                                   # frame 21

# both interfaces as sub-pixel curves
x_in,  y_in  = d[f"inner_curve_{key}"].T        # oil / air
x_out, y_out = d[f"outer_curve_{key}"].T        # water / oil (water / air where no oil)
ok_in   = d[f"inner_measured_{key}"]            # False = extrapolated
contact = d[f"outer_contact_{key}"]             # True = water / air, lies on the inner curve

# measured points only
xm, ym = x_in[ok_in], y_in[ok_in]

# local cavity radius r(y) from the per-row wall positions
y, xl, xr = d[f"inner_prof_{key}"].T
r = (xr - xl) / 2

# triple points (water / oil / air): where the outer curve joins or leaves the inner curve
j = np.flatnonzero(np.diff(contact.astype(int)))
triple_points = np.c_[x_out[j], y_out[j]]

# frames that have a cavity
frames = sorted(int(k[-5:]) for k in d.files if k.startswith("inner_curve_"))

# per-frame metrics
m = pd.read_csv("results/NAME_metrics.csv")
cavity = m[m.inner_area.notna()]
print(cavity[["time_ms", "inner_bottom_y", "oil_thickness_bottom", "water_air_contact_frac"]])

# the free surface / cut line / meniscus band used for this video
print(int(d["surface_y"]), int(d["cut_y"]), int(d["zone_bottom"]))
```

Overlaying the curves on a raw frame:

```python
import cv2, matplotlib.pyplot as plt
cap = cv2.VideoCapture("movie.avi"); cap.set(cv2.CAP_PROP_POS_FRAMES, 21)
ok, img = cap.read()
plt.imshow(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), cmap="gray")
plt.plot(x_out, y_out, "c-", lw=1)
plt.plot(x_in, y_in, "m-", lw=1)
plt.plot(x_in[~ok_in], y_in[~ok_in], "w.", ms=1)      # extrapolated points
plt.show()
```

---

## How it works

### Per frame

1. **Flat-fielding.**
   - The frame is divided by the background: `ratio = frame / background`. Water becomes ≈ 1, oil 0.4–0.8, and air < 0.3.
   - Every row is then normalised by the image margins. This removes brightness changes that are uniform along a row, e.g. from free-surface motion.
2. **Free surface and meniscus band.**
   - The free surface is the steepest bright-to-dark step of the background's row profile.
   - The *meniscus band* is the dark, striped zone below it, down to where the background has recovered towards the water level. Its horizontal stripes are the main difficulty for edge detection.
3. **Reliable lower object.** Below the band, the object is simply `ratio < 1 − t_out`.
4. **Air cavity (inner interface).**
   - The cavity is segmented by a marker-controlled **watershed** on the gradient magnitude:
     - "surely air" markers where `ratio < t_air`;
     - "surely not air" markers where `ratio > t_bright`.
   - The boundary therefore lies on the gradient ridge, not at a fixed threshold.
   - Several fixes then follow:
     - bright lensing spots inside the cavity are not used as "not air" markers;
     - small round **surface bubbles** (circle detection, tracked across frames) are excluded;
     - crater pieces cut off by a light stripe are merged back;
     - bays that a stripe cuts into a sloping wall are bridged along the slope;
     - thin dark streaks under the surface are rejected.
   - Every row is filled, because of axisymmetry.
5. **Walls near the surface.**
   - In the top `--top-rows` rows the stripes can make the wall step sideways. Steep walls are therefore re-traced upward from a clean anchor below by a 2nd-order dynamic-programming wall tracker, using the horizontal gradient only.
   - The tracker is bounded by the first bright ridge met going outward from the crater, so it cannot jump onto the oil's outer rim.
   - The shallow rims of a late, wide crater are fitted as one smooth curve instead: crater bottom → quadratic rim → free surface, with the anchor and shape searched for the best edge evidence.
   - If a wall is closed off below the surface, it is traced or extrapolated up to the surface.
6. **Whole object (outer interface).**
   - The lower object is traced upward through the band row by row, using the **local** water level just outside it.
   - A candidate is accepted if it is darker than water (the rim) or, inside the band, brighter than water (the lens-like crescent).
   - Where the oil has ended, the outline is the air wall itself (water/air contact).
7. **Sub-pixel refinement.**
   - Each contour is refined along its normals by dynamic programming (globally optimal and smooth) to the maximum of the directional derivative, with the correct polarity: dark inside, bright outside.
   - The oil/air edge may move outward only through a monotonically brightening profile, so it never crosses onto the water/oil interface.
   - The water/oil edge may move inward only down the darkening ramp into its rim.
8. **Smoothing.**
   - Loops and narrow folds are removed.
   - The curves are smoothed along their arc length (`--smooth`, 4 px). Flat stretches inside the band get stronger smoothing (`--smooth-band`, 10 px).
   - Unmeasured ends are continued smoothly up to the free surface.
9. **Water/air contact.**
   - Outer points closer than `--contact-d` (3 px) to the inner curve are water/air contact. So are unmeasured end stretches that start at the inner curve.
   - These stretches are replaced by the matching piece of the inner curve, so both curves are identical there.
   - The corners where they separate are the triple points.
10. **Metrics.** Areas, centroids and so on are computed from the final sub-pixel curves.

### Across frames (videos and stacks)

The script remembers what it found in the previous frame, and uses it in these ways:

- **Crater bottom in the band.** The bottom is only gray and striped there. The previous cavity, eroded by `--prior-erode` px, seeds "surely air". The crater bottom may sink by at most `--max-sink` px per frame inside the band, because it only rises or widens while it collapses. A new air region must overlap the previous one.
- **Surface bubbles** are tracked. A bubble missed by the detector is looked for again near its last position.
- **End of the cavity.** The cavity collapses only once. Tracking stops for good when the crater has relaxed into the free surface. That means any of these:
  - no black left in it (`--min-core-frac`);
  - flat (`--min-relief`);
  - spread into the image margins;
  - shallower than `--min-depth-track`;
  - mostly extrapolated for 2 frames.
  From then on the inner metrics are NaN, and only the leftover drop is traced.
- **Drop after the collapse.**
  - While the drop hangs from the surface, its neck inside the band is not extrapolated; the outline ends with a flat, not-measured top.
  - Once its top is visible it is traced in polar coordinates, preferring the outline most similar to the previous frame's.

Because of this, **process a sequence in order from before or at the burst**. With `--start` in the middle of a collapse, the first frames have no history and the band region can be less reliable.

---

## Measured vs. not measured

A curve point is **measured** when there is a clear edge there: an edge strength of at least `--g-meas` (0.03 per px) across the curve, and it is not in a row where the wall had to be bridged or extrapolated. Typical places where points are **not measured**:

- the top of the walls inside the meniscus band, where a stripe hides the edge;
- the short piece of wall between the last visible edge and the free surface;
- rows behind a surface bubble sitting on the wall;
- the flat top of a drop whose neck is hidden in the band.

For quantitative work, use `*_measured_*` to restrict fits to measured points. `inner_measured_frac` and `outer_measured_frac` in the CSV give a quick per-frame quality indicator.

---

## Command-line options

`python detect_interfaces.py --help` prints all of them. The defaults are tuned for the 1024×672, 10 000 fps recordings described [below](#results-on-the-10-gl-sds--3-cst-oil-recordings).

### Input, frames, output

| Option | Default | Meaning |
|---|---|---|
| `input` | — | Video, TIFF stack or image. |
| `--out` | `interfaces_out` | Output directory. |
| `--start`, `--stop`, `--step` | 0, end, 1 | Frames to process. The background is always built from the whole sequence. |
| `--fps` | 10000 | Recording frame rate, for `time_ms`. |
| `--px-per-mm` | none | Spatial calibration: metrics in mm (contours stay in px). |
| `--video-fps` | 30 | Playback rate of the annotated video. |
| `--save-frames` | off | Also write every annotated frame as a PNG. |
| `--debug i j …` | off | Write debug panels for these frames and exit. |

### Background and free surface

| Option | Default | Meaning |
|---|---|---|
| `--bg FILE` | none | Background image without the bubble. |
| `--bg-mode` | `last` | Background from the `last` or `first` N frames, or from the image `margins`. |
| `--bg-n` | 15 | N frames for the background. |
| `--no-bg-clean` | off | Do not patch objects left in the background frames. |
| `--no-row-norm` | off | Disable row-wise normalisation by the image margins. |
| `--margin-frac` | 0.10 | Width fraction of each side margin used as the reference. |
| `--surface-y` | auto | Row of the free surface. Set it if auto-detection is wrong. |
| `--surface-margin` | 6 | Rows below the free surface that are ignored; the cut line is `surface_y + this`. |
| `--surface-zone` | auto | Height of the meniscus band (px). |
| `--seed X Y` | image centre | A pixel inside the bubble, if the object is not near the centre. |

### Segmentation thresholds (ratio = frame / background; water ≈ 1)

| Option | Default | Meaning |
|---|---|---|
| `--t-air` | 0.25 | Ratio below this = surely air (watershed marker). |
| `--t-bright` | 0.55 | Ratio above this = surely not air (watershed marker). |
| `--t-air-hi` | 0.55 | A traced cavity wall needs a ratio below this just inside it. |
| `--t-out` | 0.15 | Darker than (1 − t_out) × local water = not water (the object's rim). |
| `--t-lens` | 0.20 | Inside the band, brighter than (1 + t_lens) × local water = oil too (lens effect). |
| `--air-reach` | 6 | Below the band, the cavity edge lies within this many px of "surely air" pixels. This keeps gray oil lobes out of the cavity. |
| `--min-depth-air` | 30 | A new air region must reach at least this far below the cut line; anything shallower is surface shadow. |
| `--min-area`, `--min-area-air` | 300, 150 | Minimum component areas (px²). |
| `--blur` | 1.5 | Gaussian σ for segmentation (px). |
| `--edge-sigma` | 1.0 | Gaussian σ for sub-pixel edge localisation (px). |
| `--open-r`, `--close-r`, `--open-r-air` | 2, 4, 1 | Morphology radii. |
| `--notch` | 9 | Horizontal slits up to this many rows tall are closed. |
| `--bay` | 41 | Maximum height (rows) of bays in a wall that are bridged inside the band; 0 = off. |
| `--no-satellites` | off | Do not look for small surface bubbles. |

### Walls near the surface

| Option | Default | Meaning |
|---|---|---|
| `--top-rows` | 45 | The walls in this many rows below the surface are re-traced as smooth continuations of the wall below. |
| `--dip-tol-wall` | 0.10 | A re-traced wall stops at the first bright ridge (a drop of more than this after a rise) met going outward from the crater. |
| `--shallow-slope` | 1.0 | Walls flatter than this (dy/dx) get a smooth parametric rim instead of a row-wise trace. |
| `--rim-keep` | 0.6 | The parametric rim replaces the segmented one if it has at least this fraction of its edge evidence. |

### Sub-pixel refinement, smoothing, contact

| Option | Default | Meaning |
|---|---|---|
| `--win-in-air`, `--win-out-air` | 4, 16 | px the oil/air edge may move inward or outward during refinement. It moves outward only through a brightening profile. |
| `--dip-tol` | 0.05 | Maximum darkening allowed on the way outward (oil/air). |
| `--win-in-out`, `--win-out-out` | 8, 3 | px the water/oil edge may move inward or outward. |
| `--rise-tol` | 0.05 | Maximum brightening allowed on the way inward (water/oil). |
| `--lam` | 0.06 | Stiffness of the refinement (penalty per px change of offset between neighbouring points). |
| `--smooth` | 4 | Gaussian smoothing of the final curves along their arc length (px); 0 = off. |
| `--smooth-band` | 10 | Stronger smoothing of flat stretches inside the meniscus band (px); 0 = off. |
| `--contact-d` | 3 | Closer than this (px) to the oil/air curve means no oil: water/air contact, and the curves are merged. |
| `--g-meas` | 0.03 | Minimum edge strength (1/px) for a point to count as measured. |

### Frame-to-frame tracking

| Option | Default | Meaning |
|---|---|---|
| `--prior-erode` | 12 | Inside the band, the previous cavity eroded by this many px seeds "surely air"; 0 = off. It is eroded more while the bottom rises fast. |
| `--t-prior` | 0.45 | The previous cavity seeds air only where the ratio is below this. |
| `--max-sink` | 2 | px per frame that the crater bottom may move down inside the band; −1 = off. |
| `--bottom-width` | 81 | Pockets and notches in the crater bottom inside the band that are narrower than this (px) are removed. |
| `--min-depth-track` | 15 | A tracked crater shallower than this ends the tracking. |
| `--min-relief` | 12 | A tracked crater must be at least this much deeper in the middle than at its rim; if it is flatter, tracking ends. |
| `--min-core-frac` | 0.05 | An air region needs at least this fraction of "surely air" pixels; if it has fewer, tracking ends. |
| `--no-drop-top` | off | Do not trace the top of a detached drop inside the band. |

---

## Tuning and troubleshooting

| Symptom | What to do |
|---|---|
| The orange cut line is not at the free surface. | Set `--surface-y ROW`, e.g. read from `--debug 0`. If the band limits look wrong, set `--surface-zone PX` as well. |
| The background log says a large area was patched, or the background still contains the bubble. | Use `--bg-mode first` if the first frames are clean, or give `--bg background.png`. |
| Magenta leaks into gray oil next to the cavity. | Lower `--t-bright` (e.g. 0.5) or `--air-reach` (e.g. 4). |
| Magenta sits inside the black cavity. | Raise `--t-air` slightly (e.g. 0.3). Check with `--debug` that the ratio image of the cavity is < 0.3. |
| Cyan misses a faint oil rim. | Lower `--t-out` (e.g. 0.10). |
| Curves too smooth or too wiggly. | Change `--smooth` (px), `--smooth-band` and `--lam`. |
| Tracking ends too early or too late. | Change `--min-relief`, `--min-core-frac` and `--min-depth-track`. |
| The crater bottom lags behind the image during a fast rise. | Lower `--prior-erode` (less memory) or raise `--max-sink`. |
| Different magnification or resolution. | Scale the pixel parameters: `--top-rows`, `--bay`, `--bottom-width`, `--min-depth-*`, `--min-area*`, `--smooth*`. Thresholds on the ratio need no change. |

A good first check on new data is to run `--debug` on a few frames (before the burst, mid-collapse, late collapse), then do a full run and step through `_annotated.mp4`.

---

## Accuracy and validation

These checks were run on the three distinct recordings below (frames 0–27, every 3rd frame, about 35 000 measured curve points). The offset is the distance from each measured curve point to the strongest edge along its normal.

| | median offset | 90th percentile | within 1.5 px |
|---|---|---|---|
| oil/air, below the meniscus band | 0.25 px | 0.5 px | 98 % |
| oil/air, inside the band | 0.25 px | 1.75 px | 89 % |
| water/oil, below the band | 0.25 px | 1.25 px | 91 % |

Other checks:

- **Smoothness** (RMS deviation from a 6 px-smoothed copy of the curve, 60 frames):
  - oil/air: 0.55 px in v2 → 0.28 px in v3;
  - water/oil: 0.53 px → 0.36 px.
  - Sharp turns (99th percentile of the turning angle per 3 px) are about 4 times rarer.
- **Overlap:** every outer point flagged as water/air contact lies at **0.000 px** from the inner curve, in every frame of all videos.
- **Visual review:** a separate reviewer compared the annotated collapse frames of all three videos with the raw frames, in several rounds, with zoomed checks of the problem areas.

---

## Results on the 10 g/L SDS / 3 cSt oil recordings

The recordings are Camera 2, 10 000 fps, 1024×672. S0001_2 is a byte-identical copy of S0001_1.

| Recording | Frames | Free surface y | Band until y | Cavity tracked (frames) | Median measured (oil/air) | Median water/air fraction |
|---|---|---|---|---|---|---|
| C001H001S0001_1 | 300 | 263 | 416 | 0–57 | 0.84 | 0.24 |
| C001H001S0002_1 | 226 | 285 | 418 | 0–78 | 0.93 | 0.57 |
| C001H001S0005_2 | 236 | 289 | 423 | 0–64 | 0.92 | 0.50 |

---

## Known limitations

- **Drop still attached through a hidden neck** (S0001 frames 60–180). The outline closes where the neck enters the meniscus band, so the area and centroid describe only the visible part. These frames are flagged `outer_top_in_band` / `outer_top_cut`.
- **A drop lying entirely inside the meniscus band** is not traced (S0001 after about frame 185; 106 frames without an outer curve).
- **Very shallow late crater** (S0001 frames 40–57, S0002 frames 53–55). The band's stripes are ambiguous here, and a few smooth S-shaped rises of 5–12 px remain in the rim.
- **Extrapolated ends at the surface.** Where both curves are extrapolated right below the surface, they can occasionally run up to the cut line separately (e.g. S0001 frame 32, left).
- **Thin oil lobes.** When an oil lobe beside the cavity is very thin (S0002 frames 19–20, right), part of it can be counted as air.
- **Projection.** All quantities are projected, 2-D quantities. Volumes need an axisymmetric reconstruction from `*_prof_*`.
- **Nothing above the cut line** (free surface + 6 px) is analysed.

---

## Version history

### v3 (2026-09-29): smooth profiles, water/air overlap

- Final curves are smoothed along their arc length; stronger smoothing is applied to flat stretches inside the meniscus band; loops and folds are removed; unmeasured ends are continued smoothly to the surface.
- Walls near the surface are re-traced by DP on the horizontal gradient, bounded by the first bright ridge. Shallow rims are fitted as one smooth parametric curve. Together these remove the L-shaped shelves, boxes, hooks and stripe staircases.
- Surface bubbles are tracked from frame to frame and bridged.
- Water/air contact: the outer curve is copied exactly from the inner curve wherever there is no oil. It is drawn as magenta with cyan dashes and flagged as `outer_contact_XXXXX` and `water_air_contact_frac`.
- The crater sink limit applies only to the crater bottom, not to its walls.

### v2

- Edges are placed at the gradient maximum instead of a fixed threshold. v1's oil/air curve sat 2–8 px inside the cavity.
- The cavity is segmented by a gradient watershed, and both interfaces are refined by dynamic programming along their normals.
- Handling of the meniscus band: wall tracking, crater pieces merged back, surface bubbles excluded, oil lobes kept out of the air.
- Late collapse: the curve follows the crater bottom resting on the drop, and meets the drop rims at the triple points.
- Frame-to-frame tracking: prior-seeded crater bottom, sink limit, and a clean end of the cavity (NaN metrics afterwards).
- The leftover drop is traced; detached drop tops are traced in polar coordinates.

### v1

- Fixed thresholds on the flat-fielded image, row filling, and row-wise edge tracking in the band.
