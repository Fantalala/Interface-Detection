#!/usr/bin/env python3
"""
detect_interfaces.py  (v3)
==========================

Detect and mark the interfaces of an oil-coated bubble bursting at a free
surface in high-speed shadowgraph images / videos:

    * outer interface : water | oil  (edge of the whole compound object;
                        where no oil is visible it is the water | air wall)
    * inner interface : oil | air    (edge of the air cavity / crater)

Works on videos (.avi, .mp4, ...), multi-page TIFF stacks and single images.

What changed in v3
------------------
*  Smooth profiles: the final sub-pixel curves are smoothed along their arc
   length (Gaussian, --smooth 4 px; bias < 0.2 px on the curvatures here),
   the refinement is stiffer (--lam 0.06), self-intersection loops and
   narrow folds (from sharp mask corners) are cut out, and unmeasured curve
   ends at the crater rim are continued smoothly to the free surface.
   Measured on 60 frames: RMS wiggle 0.55 -> 0.31 px, sharp turns 4x fewer;
   edge accuracy unchanged (median 0.25 px, 98 % of oil/air points within
   1.5 px below the band).
*  Top of the meniscus band: each steep crater wall is re-traced up to the
   surface (DP on the horizontal derivative, bounded by the first bright
   ridge met going out from the crater, so it cannot jump onto the oil's
   outer rim); shallow rims of the late, wide crater are fitted as one
   smooth curve (bottom -> quadratic rim -> free surface; anchor and shape
   searched for the best edge evidence) instead of following the stripes;
   flat stretches inside the band get extra smoothing (--smooth-band 10 px).
   L-shaped shelves, boxes, hooks and staircase steps from dark stripes are
   gone.  Surface bubbles touching the wall are tracked (re-detected near
   their last position) and bridged.
*  Water/air contact: where the oil has been pushed down and there is no oil
   between air and water, the water/oil curve IS the oil/air curve -- that
   stretch is copied point for point from the inner curve (both overlap
   exactly), drawn magenta with cyan dashes, and flagged per point
   (outer_contact_XXXXX in the npz); the corners where they separate are
   the triple points.
*  The crater-bottom sinking limit applies only to the bottom, no longer to
   the walls (they may move out freely as the crater widens).

What changed in v2
------------------
*  Sub-pixel edges are placed where the image actually changes fastest
   (maximum of the directional derivative across the interface), not at a
   fixed threshold level.  The v1 oil/air curve sat systematically INSIDE the
   air cavity (~2 px in the clear part, 4-8+ px in the free-surface band where
   the oil looks bright); the water/oil curve sat 1-2 px out in the water.
*  Air cavity segmented by a marker-controlled watershed on the gradient
   magnitude (boundary = gradient ridge) instead of a fixed threshold, so the
   crater walls inside the dark meniscus band are followed correctly.
*  Each interface is refined as a whole by dynamic programming along its
   normals (globally optimal, smooth, correct polarity: dark inside ->
   bright outside).  The oil/air edge may move a few px outward only through
   a monotonically brightening profile, never across a bright ridge + dark
   valley (i.e. never onto the water/oil interface); the water/oil edge may
   move inward only down the darkening ramp into its dark rim (soft,
   defocused rims no longer put it 4-6 px out in the water).
*  Late collapse, crater resting on the oil drop: the oil/air interface is the
   lower edge of the black crater, which meets the drop's water/oil rims at
   the triple points (v1 cut across the gray band in between).
*  Free-surface band: walls hidden by a light stripe are traced by a
   2nd-order DP wall tracker and kept only where a real edge agrees with the
   smooth continuation of the wall; the rest is extrapolated smoothly and
   flagged as not measured.  Crater pieces cut off by a light stripe are
   merged back, and bays it cuts into a sloping wall are bridged along the
   slope (v1 produced vertical steps).  Small round bubbles floating at the
   surface (circle detection, tracked from frame to frame) are excluded from
   the cavity.  The water/oil outline is traced with a LOCAL water level (v1
   capped it at 1, so it lost the rim and jumped onto the cavity wall), also
   accepts the bright lens-like oil crescent of the band, and switches to the
   air wall where the oil shell has ended (water/air contact).
*  Consistency: the outer interface always encloses the inner one; where
   they are within 1 px they are the same (water/air) curve.  Masks, areas
   and wall profiles are derived from the final sub-pixel curves.
*  Sequences (video / stack): what is known from the previous frame is used.
   Inside the band the crater bottom is only gray and striped, so the
   previous cavity (eroded) seeds 'surely air', the crater may not sink by
   more than --max-sink px per frame (it only rises / widens while it
   collapses and relaxes), and a new air region must overlap the previous
   one.  Tracking ends -- once, for good -- when the crater has relaxed: no
   black left in it, flat (relief < --min-relief), spread into the image
   margins, or mostly extrapolated for 2 frames.  Surface bubbles are tracked.
*  The drop left behind: while it hangs from the surface, its neck hidden in
   the band is not extrapolated -- the outline ends where the edge is lost
   (flat top flagged as not measured).  Once the drop's top is visible in the
   band it is traced in polar coordinates (lens-like bright top, either
   polarity) instead of the pointed extrapolation of v1/early v2.
   A drop lying entirely inside the band is not traced.  Caveat: a drop that
   still hangs from the surface by a neck hidden in the band can get an
   outline closed where the neck meets the band; the CSV columns
   outer_top_cut / outer_top_in_band mark such frames (use the drop's area,
   centroid, ... there only as 'visible part below the band').

Method (per frame)
------------------
1.  Flat-field: ratio = frame / background (median of the last N frames,
    leftover objects patched), every row normalised by the image margins.
2.  Free surface = steepest bright->dark step of the background row profile;
    the dark meniscus band below it is the "free-surface zone".
3.  Lower object (below the zone): ratio < 1 - t_out, largest central blob.
4.  Air: watershed of |grad ratio| with markers  air: ratio < t_air,
    not-air: ratio > t_bright (lensing spots inside the cavity and surface
    bubbles handled); the cavity component, crater pieces cut off by a light
    stripe merged back, bays bridged, rows filled (axisymmetric object: every
    horizontal cut is one interval).  If the cavity is closed below the free
    surface, its walls are traced/extrapolated up to it.
5.  Outer: lower object + outline traced upward through the zone + air
    (after the collapse: drop outline, top traced in polar coordinates).
6.  Contours -> sub-pixel refinement (DP along normals) -> containment ->
    measured / not-measured flag per point.
7.  (sequences) the result is carried to the next frame (see above).

Outputs (in --out directory)
----------------------------
    <name>_annotated.mp4    frames with outer (cyan) / inner (magenta) interfaces;
                            magenta with cyan dashes = both (water/air, no oil);
                            thin light line = not measured, extrapolated
    <name>_metrics.csv      per-frame areas, equivalent radii, bottom positions,
                            oil-film thickness at the bottom, centroids, fraction
                            of measured points, flags (NaN = no such interface)
    <name>_contours.npz     per frame i:
                              outer_curve_XXXXX / inner_curve_XXXXX  the interface as
                                  ONE continuous ordered sub-pixel curve (x, y),
                                  free surface (left) -> bottom -> free surface (right)
                              outer_measured_XXXXX / inner_measured_XXXXX  boolean
                                  per curve point: False where the interface was
                                  hidden and extrapolated / has no clear edge
                              outer_strength_XXXXX / inner_strength_XXXXX  edge
                                  strength (d ratio / d n, 1/px) per curve point
                              outer_contact_XXXXX  boolean per outer-curve point:
                                  True = water/air contact, the point lies on the
                                  inner curve (no oil there)
                              outer_XXXXX / inner_XXXXX            closed pixel contours
                              outer_prof_XXXXX / inner_prof_XXXXX  sub-pixel wall
                                  profiles, columns (y, x_left, x_right)
    <name>_profiles.png     all interface curves overlaid, coloured by time
    <name>_debug_XXXX.png   (with --debug) ratio image + masks for a frame

Reading the results later:
    d = np.load("..._contours.npz")
    x, y = d["inner_curve_00021"].T              # cavity interface, frame 21
    ok = d["inner_measured_00021"]               # measured points only: x[ok], y[ok]
    y, xl, xr = d["inner_prof_00021"].T          # cavity wall, frame 21
    r = (xr - xl) / 2                            # local cavity radius r(y)

Usage examples
--------------
    python detect_interfaces.py movie.avi
    python detect_interfaces.py movie.avi --stop 36            # collapse only
    python detect_interfaces.py stack.tif --fps 10000 --px-per-mm 50
    python detect_interfaces.py stack.tif --debug 0 20 30      # inspect frames
    python detect_interfaces.py movie.avi --surface-y 165
    python detect_interfaces.py single.png --bg background.png

Requires: numpy, opencv-python, scipy, scikit-image
          (matplotlib for the plot, tifffile for big TIFFs)
"""

import argparse
import csv
import os
import sys

import cv2
import numpy as np
from scipy.ndimage import gaussian_filter1d, map_coordinates

OUTER_COLOR = (255, 255, 0)    # BGR cyan    -> water/oil interface
INNER_COLOR = (255, 0, 255)    # BGR magenta -> oil/air interface
SURF_COLOR = (0, 200, 255)     # BGR orange  -> free-surface cut line

VIDEO_EXT = {".avi", ".mp4", ".mov", ".mkv", ".wmv", ".m4v", ".mpg", ".mpeg"}


# --------------------------------------------------------------------------- #
#  I/O
# --------------------------------------------------------------------------- #
def to_gray(img):
    """Convert any image to float32 grayscale (0-255 scale)."""
    if img.ndim == 3:
        if img.shape[2] == 4:
            img = img[:, :, :3]
        img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    img = img.astype(np.float32)
    if img.max() > 255:                          # 12/16-bit camera data
        img = img * (255.0 / max(img.max(), 1))
    return img


def load_frames(path, start=0, stop=None, step=1):
    """Return (list of float32 gray frames, list of frame indices)."""
    ext = os.path.splitext(path)[1].lower()
    frames, idx = [], []

    if ext in VIDEO_EXT:
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            sys.exit(f"Could not open video {path}")
        i = 0
        while True:
            ok, f = cap.read()
            if not ok or (stop is not None and i >= stop):
                break
            if i >= start and (i - start) % step == 0:
                frames.append(to_gray(f))
                idx.append(i)
            i += 1
        cap.release()
    else:
        stack = None
        try:
            import tifffile
            if ext in (".tif", ".tiff"):
                stack = tifffile.imread(path)
                if stack.ndim == 2 or (stack.ndim == 3 and stack.shape[-1] in (3, 4)):
                    stack = stack[None]
        except ImportError:
            pass
        if stack is None:
            ok, stack = cv2.imreadmulti(path, flags=cv2.IMREAD_UNCHANGED)
            if not ok or len(stack) == 0:
                img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
                if img is None:
                    sys.exit(f"Could not read {path}")
                stack = [img]
        n = len(stack)
        stop = n if stop is None else min(stop, n)
        for i in range(start, stop, step):
            frames.append(to_gray(np.asarray(stack[i])))
            idx.append(i)

    if not frames:
        sys.exit("No frames loaded - check --start/--stop.")
    return frames, idx


# --------------------------------------------------------------------------- #
#  Background & free surface
# --------------------------------------------------------------------------- #
def background_from_margins(frame, margin_frac=0.10):
    """Row-wise background from the left/right margins (single-image case)."""
    h, w = frame.shape
    m = max(5, int(w * margin_frac))
    side = np.hstack([frame[:, :m], frame[:, -m:]])
    col = np.median(side, axis=1)
    col = cv2.GaussianBlur(col.reshape(-1, 1), (1, 0), 2).ravel()
    return np.repeat(col[:, None], w, axis=1).astype(np.float32)


def horizontal_trend(img, width_frac=0.4):
    """Running median along rows (window = width_frac * image width):
    follows the slowly varying / slightly tilted stratified background but
    ignores compact objects narrower than ~half the window."""
    from scipy.ndimage import median_filter
    h, w = img.shape
    s = 4
    small = cv2.resize(img, (w // s, h // s), interpolation=cv2.INTER_AREA)
    k = max(3, int(width_frac * w / s) | 1)
    med = median_filter(small, size=(1, k), mode="nearest")
    return cv2.resize(med, (w, h), interpolation=cv2.INTER_LINEAR).astype(np.float32)


def clean_background(bg, t=0.12, min_area=150, grow=15):
    """
    Remove objects that are still present in the background frames (e.g. the
    oil drop left hanging under the surface at the end of the recording).
    The background is horizontally stratified, so any compact blob deviating
    from a wide horizontal running median by more than `t` is replaced by it.
    Returns (cleaned background, patched-pixel mask).
    """
    m = horizontal_trend(bg)
    dev = (np.abs(bg / np.maximum(m, 1.0) - 1.0) > t).astype(np.uint8)
    dev = cv2.morphologyEx(dev, cv2.MORPH_OPEN, disk(1))
    n, lab, st, _ = cv2.connectedComponentsWithStats(dev, 8)
    bad = np.isin(lab, [k for k in range(1, n) if st[k, cv2.CC_STAT_AREA] >= min_area])
    bad = cv2.dilate(bad.astype(np.uint8), disk(grow)) > 0
    if not bad.any():
        return bg, bad
    wgt = cv2.GaussianBlur(bad.astype(np.float32), (0, 0), grow / 2)
    wgt = np.maximum(wgt, bad)
    return (bg * (1 - wgt) + m * wgt).astype(np.float32), bad


def estimate_background(frames, mode="last", n=15, clean=True):
    if mode == "margins" or len(frames) == 1:
        return None                                  # computed per frame
    stack = np.stack(frames[-n:] if mode == "last" else frames[:n])
    bg = np.median(stack, axis=0).astype(np.float32)
    if clean:
        bg, bad = clean_background(bg)
        if bad.any():
            ys, xs = np.nonzero(bad)
            print(f"  background: patched leftover object(s) in x={xs.min()}-{xs.max()}, "
                  f"y={ys.min()}-{ys.max()} ({bad.mean() * 100:.1f}% of image)")
    return bg


def detect_surface_y(bg_or_frame, search=(0.05, 0.6)):
    """
    Free surface = steepest bright->dark step of the row-mean profile in the
    upper part of the image (the meniscus band in these shadowgraphs).
    """
    h = bg_or_frame.shape[0]
    prof = cv2.GaussianBlur(bg_or_frame.mean(axis=1).reshape(-1, 1), (1, 0), 3).ravel()
    g = np.gradient(prof)
    lo, hi = int(search[0] * h), int(search[1] * h)
    return int(lo + np.argmin(g[lo:hi]))


def detect_zone_bottom(ref, surface_y, frac=0.3):
    """
    Bottom of the dark meniscus band below the free surface: first row below
    the band minimum where the background has recovered `frac` of the way
    back to the water level.
    """
    prof = cv2.GaussianBlur(ref.mean(axis=1).reshape(-1, 1), (1, 0), 3).ravel()
    h = len(prof)
    water = np.median(prof[int(0.7 * h):])
    seg = prof[surface_y:]
    y_min = surface_y + int(np.argmin(seg[: max(10, h // 3)]))
    level = prof[y_min] + frac * (water - prof[y_min])
    above = np.where(prof[y_min:] >= level)[0]
    return int(y_min + above[0]) if above.size else h - 1


# --------------------------------------------------------------------------- #
#  Morphology / geometry helpers
# --------------------------------------------------------------------------- #
def disk(r):
    r = max(1, int(r))
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))


def fill_rows(mask):
    """
    Fill every row of a mask between its leftmost and rightmost pixel.
    Justified because the bubble / drop / crater is axisymmetric about a
    vertical axis: any horizontal cut through a body of revolution projects to
    ONE interval.  Closes U-shaped oil 'bowls' whose flat top is invisible in
    shadowgraphy and fills the bright lensing spot in the middle of the air.
    """
    out = np.zeros_like(mask)
    rows = np.where(mask.any(axis=1))[0]
    for r in rows:
        c = np.flatnonzero(mask[r])
        out[r, c[0]:c[-1] + 1] = 255
    return out


def row_edges(mask):
    """Per row: first / last occupied column (NaN where the row is empty)."""
    H = mask.shape[0]
    xl = np.full(H, np.nan)
    xr = np.full(H, np.nan)
    idx = np.where(mask.any(axis=1))[0]
    if idx.size:
        m = mask[idx] > 0
        xl[idx] = np.argmax(m, axis=1)
        xr[idx] = m.shape[1] - 1 - np.argmax(m[:, ::-1], axis=1)
    return xl, xr


def pick_component(mask, seed=None, min_area=200, row_fill=True):
    """Keep one connected component: the one containing/closest to seed
    (default: big and close to the image centre).  Optionally row-filled."""
    n, lab, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    if n <= 1:
        return np.zeros_like(mask)
    h, w = mask.shape
    sx, sy = seed if seed is not None else (w / 2, h / 2)
    best, best_score = None, None
    for k in range(1, n):
        if stats[k, cv2.CC_STAT_AREA] < min_area:
            continue
        comp = np.where(lab == k, 255, 0).astype(np.uint8)
        if row_fill:
            comp = fill_rows(cv2.morphologyEx(comp, cv2.MORPH_CLOSE,
                                              np.ones((5, 1), np.uint8)))
        if seed is not None and comp[int(sy), int(sx)]:
            return comp
        ys, xs = np.nonzero(comp)
        d = np.hypot(xs.mean() - sx, ys.mean() - sy)
        score = xs.size / (1.0 + d / 50.0)            # big & central wins
        if best_score is None or score > best_score:
            best, best_score = comp, score
    return best if best is not None else np.zeros_like(mask)


def remove_notches(mask, cut, row_fill=True, h=5):
    """Close horizontal notches/slits only a few rows tall (edge noise), which
    would otherwise make the contour run into the slit and back."""
    if not mask.any():
        return mask
    m = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((h, 1), np.uint8))
    m[:cut] = 0
    return fill_rows(m) if row_fill else m


def snap_to_surface(mask, cut, snap=15, frac=0.5, look=10):
    """If the (row-filled) mask reaches its full width only a few px below the
    free-surface cut line -- a thin bright line at the surface, or only a
    narrow sliver above -- continue that first full row straight up to the cut,
    so the interface ends on the free surface instead of closing with an
    artificial lid.  Returns (mask, (y_from, y_to) of replaced rows or None)."""
    ys = np.where(mask.any(axis=1))[0]
    if ys.size == 0:
        return mask, None
    xl, xr = row_edges(mask)
    w = np.nan_to_num(xr - xl + 1)
    y_s = None
    for y in range(int(ys[0]), min(cut + snap, int(ys[-1])) + 1):
        if w[y] > 0 and w[y] >= frac * w[y:y + look].max():
            y_s = y
            break
    if y_s is None or y_s <= cut or y_s - cut > snap:
        return mask, None
    out = mask.copy()
    out[cut:y_s] = mask[y_s]
    return out, (cut, y_s)


# --------------------------------------------------------------------------- #
#  Ratio image & gradients
# --------------------------------------------------------------------------- #
def compute_images(frame, bg, p):
    """ratio (for segmentation, sigma = --blur), edge ratio (for sub-pixel edge
    localisation, sigma = --edge-sigma) and the gradients of the latter."""
    if bg is None:
        bg = background_from_margins(frame)
    b = cv2.GaussianBlur(bg, (0, 0), max(p.blur, 2.0)) + 5.0
    R = cv2.GaussianBlur(frame, (0, 0), p.blur) / b
    Re = cv2.GaussianBlur(frame, (0, 0), p.edge_sigma) / b
    if p.row_norm:
        # remove horizontally-uniform changes (free surface moving up/down):
        # normalise every row by the ratio measured at the image margins
        norm = background_from_margins(R, p.margin_frac).clip(0.05)
        R, Re = R / norm, Re / norm
    R, Re = R.astype(np.float32), Re.astype(np.float32)
    gx = cv2.Sobel(Re, cv2.CV_32F, 1, 0, ksize=3) / 8.0
    gy = cv2.Sobel(Re, cv2.CV_32F, 0, 1, ksize=3) / 8.0
    return R, Re, gx, gy


# --------------------------------------------------------------------------- #
#  Air cavity (inner interface) segmentation
# --------------------------------------------------------------------------- #
def segment_air(R, gx, gy, cut, zone_bottom, obj_x, p, satellites=(), prior=None, erode=None):
    """
    Marker-controlled watershed of the gradient magnitude: the boundary of the
    air region is the gradient ridge between 'surely air' (ratio < t_air) and
    'surely not air' (ratio > t_bright).  Unlike a fixed threshold this
    follows crater walls whose interior is only dark gray (meniscus band).
    """
    from skimage.segmentation import watershed
    H, W = R.shape
    mk = np.zeros((H, W), np.int32)
    core = cv2.morphologyEx((R < p.t_air).astype(np.uint8), cv2.MORPH_OPEN, disk(1))
    core[:cut] = 0
    # small dark spots below the band that are not part of the cavity (caustics
    # in the rim of an oil lobe) are no 'surely air' seeds
    nc, lc, sc, _ = cv2.connectedComponentsWithStats(core, 8)
    if nc > 2:
        small = np.flatnonzero((sc[:, cv2.CC_STAT_AREA] < 100) &
                               (sc[:, cv2.CC_STAT_TOP] >= zone_bottom))
        small = small[small > 0]
        if small.size:
            core[np.isin(lc, small)] = 0
    mk[core > 0] = 1
    erode = p.prior_erode if erode is None else erode
    if prior is not None and erode > 0:
        pm = cv2.erode(prior, disk(erode)) > 0
        pm[zone_bottom:] = False
        pm &= R < p.t_prior
        # not the gray layer right above a (bright, lens-like) drop top
        kb = np.ones((16, 1), np.uint8)
        above_bright = cv2.dilate((R > 1.0).astype(np.uint8), kb, anchor=(0, 0)) > 0
        pm &= ~above_bright
        mk[pm] = 1
    bright = (R > p.t_bright).astype(np.uint8)
    bright[:cut] = 0
    # bright lensing spots INSIDE the cavity are not 'surely not air': as
    # markers they would claim the gray stripes of the meniscus band that
    # cross the crater.  Such a spot is not connected to the surrounding water
    # (image sides) and has air on both sides (same row) or above and below
    # (same column).
    cz = core.copy()
    cz[:cut] = 0
    if obj_x is not None:
        cz[:, :max(int(obj_x[0]), 0)] = 0
        cz[:, int(obj_x[1]) + 1:] = 0
    cum = lambda a, ax: np.maximum.accumulate(a, axis=ax) > 0
    enclosed = (cum(cz, 1) & cum(cz[:, ::-1], 1)[:, ::-1]) | \
               (cum(cz, 0) & cum(cz[::-1], 0)[::-1])
    nb, lb, sb, _ = cv2.connectedComponentsWithStats(bright, 8)
    if nb > 1:
        frac = np.bincount(lb.ravel(), weights=enclosed.ravel(), minlength=nb) / np.maximum(sb[:, 4], 1)
        side = np.zeros(nb, bool)
        side[np.unique(lb[:, 0])] = True
        side[np.unique(lb[:, -1])] = True
        drop = np.flatnonzero((frac >= 0.6) & ~side)
        drop = drop[drop > 0]
        if drop.size:
            bright[np.isin(lb, drop)] = 0
    mk[bright > 0] = 2
    for x, y, r in satellites:                 # satellite bubbles are not the cavity
        cv2.circle(mk, (int(round(x)), int(round(y))), int(round(r + 3)), 2, -1)
    mk[:cut] = 0
    valid = np.zeros((H, W), bool)
    valid[cut:] = True
    lab = watershed(np.hypot(gx, gy), mk, mask=valid)
    air = ((lab == 1) & valid).astype(np.uint8) * 255
    air = cv2.morphologyEx(air, cv2.MORPH_OPEN, disk(p.open_r_air))
    n, labc, st, _ = cv2.connectedComponentsWithStats(air, 8)
    best, best_a = None, 0
    for k in range(1, n):
        a = st[k, cv2.CC_STAT_AREA]
        top, hgt = st[k, cv2.CC_STAT_TOP], st[k, cv2.CC_STAT_HEIGHT]
        x0 = st[k, cv2.CC_STAT_LEFT]
        x1 = x0 + st[k, cv2.CC_STAT_WIDTH]
        if a < p.min_area_air or top + hgt < cut + 12:      # thin surface streaks
            continue
        if obj_x is not None and (x1 < obj_x[0] or x0 > obj_x[1]):
            continue
        if a > best_a:
            best, best_a = k, a
    if best is None:
        return np.zeros((H, W), np.uint8)
    air = np.where(labc == best, 255, 0).astype(np.uint8)
    if p.air_reach > 0 and zone_bottom < H:
        # below the meniscus band the cavity is black: its edge lies within a
        # few px of 'surely air' pixels.  Dark-gray regions further away (the
        # rim of an oil lobe beside the cavity) are not air -- flooding them
        # and then filling rows would count the whole lobe as air.
        near = cv2.dilate(core, disk(p.air_reach)) > 0
        low = air[zone_bottom:] > 0
        air[zone_bottom:] = np.where(low & near[zone_bottom:], 255, 0).astype(np.uint8)
        n2, l2, s2, _ = cv2.connectedComponentsWithStats(air, 8)
        if n2 > 2:
            air = np.where(l2 == 1 + int(np.argmax(s2[1:, cv2.CC_STAT_AREA])), 255, 0).astype(np.uint8)
    air = fill_rows(air)
    air = merge_upper_parts(air, labc, st, n, best, cut)
    if p.bay > 1:
        # other dark pieces of the crater inside the band, cut off by a light
        # stripe but vertically within bridging distance of the cavity
        near = cv2.dilate(air, np.ones((2 * p.bay + 1, 1), np.uint8))
        cx = np.where(air.any(axis=0))[0]
        for k in range(1, n):
            if k == best or st[k, cv2.CC_STAT_AREA] < 60:
                continue
            t, h = st[k, cv2.CC_STAT_TOP], st[k, cv2.CC_STAT_HEIGHT]
            x0, w = st[k, cv2.CC_STAT_LEFT], st[k, cv2.CC_STAT_WIDTH]
            if t + h > zone_bottom or x0 < cx[0] - 30 or x0 + w > cx[-1] + 30:
                continue
            comp = labc == k
            if (near[comp] > 0).any():
                air[comp] = 255
        air = fill_bays(fill_rows(air), cut, zone_bottom, p.bay)
    air = clean_bottom(air, cut, zone_bottom, p.bottom_width, depth=4)
    air = trim_top_flare(air, cut)
    return remove_notches(fill_rows(air), cut, True, p.notch)


def fill_bays(air, cut, zone_bottom, height=41, depth=8.0):
    """
    Bays in a cavity wall inside the meniscus band: a light stripe of the band
    crossing the crater can make a run of rows (<= `height`) look like
    'not air' near one wall, so that wall jumps inward and back out.  Per
    side, rows whose wall lies more than `depth` px inward of a 1-D
    morphological opening of the wall position x(y) are such a bay; they are
    replaced by linear interpolation between the rows just above and below
    it (sloping crater walls stay sloped, unlike a vertical 2-D closing).
    """
    xl, xr = row_edges(air)
    ys = np.where(~np.isnan(xl))[0]
    if ys.size < 5:
        return air
    y0, y1 = int(ys[0]), int(ys[-1])
    from scipy.ndimage import grey_opening
    walls = []
    changed = False
    for f in (xl[y0:y1 + 1].copy(), -xr[y0:y1 + 1].copy()):   # inward = larger
        f = np.where(np.isnan(f), np.nanmax(f), f)
        op = grey_opening(f, size=height | 1, mode="nearest")
        bay = (f - op > depth)
        rows = np.arange(y0, y1 + 1)
        bay &= (rows >= cut) & (rows < zone_bottom)
        g = f.copy()
        idx = np.flatnonzero(bay)
        if idx.size:
            runs = np.split(idx, np.flatnonzero(np.diff(idx) > 1) + 1)
            for r in runs:
                a, b = r[0] - 1, r[-1] + 1
                if a < 0 or b >= f.size or r.size > height:
                    continue
                g[r] = np.interp(r, [a, b], [f[a], f[b]])
                changed = True
        walls.append(g)
    if not changed:
        return air
    out = air.copy()
    for k, y in enumerate(range(y0, y1 + 1)):
        a, b = walls[0][k], -walls[1][k]
        if np.isnan(a) or np.isnan(b):
            continue
        a, b = int(round(a)), int(round(b))
        if b > a:
            out[y] = 0
            out[y, max(a, 0):b + 1] = 255
    return out


def trim_top_flare(air, cut, depth=12, max_step=6.0):
    """Right under the free surface a dark streak can join the cavity, or a
    light line can cut into it, so that its top rows jump sideways (a real wall
    changes by a few px per row there, not tens).  Within the top `depth` rows,
    from the lowest such jump upward, each wall is continued with the slope of
    the rows below it."""
    xl, xr = row_edges(air)
    ys = np.where(~np.isnan(xl))[0]
    if ys.size < depth + 6 or ys[0] > cut + 1:
        return air
    y_top = int(ys[0])
    changed = False
    walls = [xl.copy(), xr.copy()]
    for side, w in enumerate(walls):
        for y in range(y_top + depth, y_top - 1, -1):
            if np.isnan(w[y]) or np.isnan(w[y + 1]):
                continue
            if abs(w[y] - w[y + 1]) > max_step:
                yb = np.arange(y + 1, y + 7)
                sl = np.polyfit(yb, w[yb], 1)[0] if np.isfinite(w[yb]).all() else 0.0
                sl = float(np.clip(sl, -4, 4))
                w[y_top:y + 1] = w[y + 1] + sl * (np.arange(y_top, y + 1) - (y + 1))
                changed = True
                break
    if not changed:
        return air
    out = air.copy()
    for y in range(y_top, y_top + depth + 1):
        a, b = walls[0][y], walls[1][y]
        out[y] = 0
        if not (np.isnan(a) or np.isnan(b)) and b > a:
            out[y, max(int(round(a)), 0):int(round(b)) + 1] = 255
    return out


def clean_bottom(air, cut, zone_bottom, width=41, depth=6, max_depth=40):
    """
    Crater bottom inside the meniscus band (late collapse, crater resting on
    the drop): the bottom y_b(x) is a smooth, wide curve.  Narrow downward
    pockets (the cavity wrapping around a small bubble sitting on the drop,
    a dark stripe end) and narrow upward notches / spikes (a light stripe),
    narrower than `width` px and between `depth` and `max_depth` px deep, are
    removed with a 1-D grey opening / closing of y_b(x).
    """
    from scipy.ndimage import grey_closing, grey_opening
    m = air > 0
    cols = np.flatnonzero(m.any(axis=0))
    if cols.size < width:
        return air
    H = air.shape[0]
    yb = (H - 1 - np.argmax(m[::-1, cols], axis=0)).astype(float)
    out = air.copy()
    inband = yb < zone_bottom
    op = grey_opening(yb, size=width, mode="nearest")
    pocket = inband & (yb - op > depth) & (yb - op <= max_depth)
    cl = grey_closing(yb, size=width, mode="nearest")
    notch = inband & (cl - yb > depth) & (cl - yb <= max_depth) & (cl < zone_bottom)
    for k in np.flatnonzero(pocket):
        out[int(op[k]) + 1:, cols[k]] = 0
    for k in np.flatnonzero(notch):
        out[int(yb[k]) + 1:int(cl[k]) + 1, cols[k]] = 255
    return out


def crater_relief(air):
    """Depth of the crater below its own rim: deepest point of the middle half
    of the air region minus the median bottom of its outer 10 % on each side
    (a relaxed crater is a flat band: relief ~ 0)."""
    m = air > 0
    cols = np.flatnonzero(m.any(axis=0))
    if cols.size < 20:
        return 0.0
    yb = (m.shape[0] - 1 - np.argmax(m[::-1, cols], axis=0)).astype(float)
    n = cols.size
    mid = yb[n // 4:3 * n // 4]
    ends = np.r_[yb[:max(n // 10, 1)], yb[-max(n // 10, 1):]]
    return float(mid.max() - np.median(ends))


def find_satellites(R, cut, zone_bottom, rmin=6, rmax=22, param2=18, lower=None, near=None,
                    t_air=0.25):
    """Small round bubbles / drops floating at the free surface (left over
    from earlier bursts) inside the meniscus band: circle Hough transform.
    Circles overlapping the (reliable) lower object are its oil lobes, not
    bubbles.  `near` = list of (x, y, r): search only around these positions
    (re-detection of tracked bubbles with a lower threshold).
    Returns a list of (x, y, r)."""
    H, W = R.shape
    y1 = min(zone_bottom + 20, H)
    if y1 - cut < 2 * rmin + 2:
        return []
    img = cv2.GaussianBlur(np.clip(R / 1.6 * 255, 0, 255).astype(np.uint8), (0, 0), 1.5)
    windows = [(cut, y1, 0, W)] if near is None else \
        [(max(int(y - r - 25), cut), min(int(y + r + 25), y1), max(int(x - r - 25), 0),
          min(int(x + r + 25), W)) for x, y, r in near]
    out = []
    for (a, b, c, d) in windows:
        if b - a < 2 * rmin + 2 or d - c < 2 * rmin + 2:
            continue
        cs = cv2.HoughCircles(img[a:b, c:d], cv2.HOUGH_GRADIENT, dp=1, minDist=12, param1=60,
                              param2=param2, minRadius=rmin, maxRadius=rmax)
        if cs is None:
            continue
        for x, y, r in cs[0][:1] if near is not None else cs[0]:
            x, y, r = float(x) + c, float(y) + a, float(r)
            m = np.zeros((H, W), np.uint8)
            cv2.circle(m, (int(round(x)), int(round(y))), int(round(r)), 1, -1)
            if lower is not None and (lower[m > 0] > 0).mean() > 0.2:
                continue                              # an oil lobe of the object
            rows_c = np.arange(max(int(y - r / 2), cut), min(int(y + r / 2), H - 1) + 1)
            both = [(R[yy, :max(int(x - r - 2), 1)] < t_air).any() and
                    (R[yy, min(int(x + r + 2), W - 1):] < t_air).any() for yy in rows_c]
            if both and np.mean(both) > 0.5:
                continue                              # a lensing spot inside the crater
            if any(np.hypot(x - q[0], y - q[1]) < max(r, q[2]) for q in out):
                continue                              # duplicate
            out.append((x, y, r))
    return out


def side_anchor(xw, y_top, y_bot, cut, brk=12.0, max_gap=90):
    """Top row of the reliable part of one wall: top of the longest stretch of
    rows without a jump > `brk` px (a jump = rounded corner of an air region
    closed below the surface, a surface-shadow piece, a hook), with the
    rounded-corner rows at its top trimmed off."""
    ys = np.arange(y_top, y_bot + 1)
    x = xw[ys]
    good = ~np.isnan(x)
    d = np.full(ys.size, np.inf)
    d[1:] = np.abs(np.diff(x))
    brk_ = ~good | (d > brk)
    brk_[0] = True
    starts = np.flatnonzero(brk_)
    ends = np.append(starts[1:], ys.size)
    k = int(np.argmax(ends - starts))
    s, e = int(starts[k]), int(ends[k])
    if e - s < 8:
        return None
    dd = np.abs(np.diff(x[s:e]))
    med = float(np.median(dd[3:25])) if dd.size > 6 else 1.0
    j = 0
    while j < dd.size - 8 and dd[j] > max(2.0, 3 * med):
        j += 1
    y = int(ys[s + j])
    return y if y - cut <= max_gap else None


def merge_upper_parts(main, labc, st, n, best, cut, flare=3.0):
    """A horizontal light stripe of the meniscus band can cut the upper part
    of the crater off the main cavity.  Dark parts lying above the main
    cavity, within the range its walls can reach (<= `flare` px/row), are
    merged and the walls are bridged linearly across the stripe."""
    H = main.shape[0]
    ys = np.where(main.any(axis=1))[0]
    if ys.size == 0 or ys[0] <= cut + 3:
        return main
    top = int(ys[0])
    xl, xr = row_edges(main)
    ya = [side_anchor(xl, top, int(ys[-1]), cut), side_anchor(xr, top, int(ys[-1]), cut)]
    if any(a is None for a in ya):
        return main
    up = np.zeros_like(main)
    for k in range(1, n):
        if k == best:
            continue
        t, h = st[k, cv2.CC_STAT_TOP], st[k, cv2.CC_STAT_HEIGHT]
        x0, w = st[k, cv2.CC_STAT_LEFT], st[k, cv2.CC_STAT_WIDTH]
        bot = t + h - 1
        if st[k, cv2.CC_STAT_AREA] < 60 or bot >= top + 3:
            continue
        fl = flare * (max(ya) - bot) + 20
        lo, hi = xl[ya[0]] - fl, xr[ya[1]] + fl
        if x0 < lo or x0 + w - 1 > hi or x0 + w - 1 < xl[ya[0]] or x0 > xr[ya[1]]:
            continue
        up |= np.where(labc == k, 255, 0).astype(np.uint8)
    if not up.any():
        return main
    up = fill_rows(up)
    uys = np.where(up.any(axis=1))[0]
    ul, ur = row_edges(up)
    ub = int(uys[-1])
    # bottom anchors of the upper part (skip its rounded lower corners)
    bl = side_anchor(ul[::-1], H - 1 - ub, H - 1 - int(uys[0]), H)
    br = side_anchor(ur[::-1], H - 1 - ub, H - 1 - int(uys[0]), H)
    ubl = ub if bl is None else H - 1 - bl
    ubr = ub if br is None else H - 1 - br
    out = main.copy()
    out[:max(ya)] = 0
    wl = np.full(H, np.nan)
    wr = np.full(H, np.nan)
    wl[uys[0]:ubl + 1] = ul[uys[0]:ubl + 1]
    wr[uys[0]:ubr + 1] = ur[uys[0]:ubr + 1]
    wl[ya[0]:] = xl[ya[0]:]
    wr[ya[1]:] = xr[ya[1]:]
    rows = np.arange(uys[0], max(ya) + 1)
    for w_ in (wl, wr):
        k = ~np.isnan(w_[rows])
        w_[rows] = np.interp(rows, rows[k], w_[rows][k])
    for r in rows:
        a, b = int(round(wl[r])), int(round(wr[r]))
        out[r] = 0
        if b > a:
            out[r, max(a, 0):b + 1] = 255
    return out


# --------------------------------------------------------------------------- #
#  Wall tracking inside the free-surface band
# --------------------------------------------------------------------------- #
def interp_rows(img, ys, xs):
    """img sampled at integer rows ys (len R) x float columns xs (len S)."""
    w = img.shape[1]
    x = np.clip(xs, 0, w - 1.001)
    x0 = np.floor(x).astype(int)
    fx = x - x0
    rows = img[ys]
    return rows[:, x0] * (1 - fx) + rows[:, x0 + 1] * fx


def track_wall(gx, gy, side, y0, x0, y1, slope0=0.0, win=60, step=0.5, max_slope=3.0,
               mu=0.012, cap=0.05, in_ok=None, blind=None, xonly=False):
    """
    Trace one wall (side 0 = left, 1 = right) upward from anchor x0 at row y0
    to row y1 < y0 by 2nd-order dynamic programming:
      state   (x, dx),  dx = x(y) - x(y+1),  |dx| <= max_slope px/row
      reward  outward directional derivative of the ratio across the wall
              (dark inside -> bright outside), saturated at `cap`, and only
              where in_ok(rows, xs) holds (e.g. the inner side is dark)
      penalty mu per 0.5 px change of dx between rows (curvature)
    Where there is no evidence (or in `blind` rows) the path continues straight.
    Returns rows (y0-1 .. y1), x path, derivative D along the path.
    """
    sgn = -1.0 if side == 0 else 1.0                       # outward x direction
    xs = np.arange(x0 - win, x0 + win + step / 2, step)
    dxs = np.arange(-max_slope, max_slope + step / 2, step)
    S, K = len(xs), len(dxs)
    rows = np.arange(y0 - 1, y1 - 1, -1)
    if rows.size == 0:
        return rows, np.array([]), np.array([])
    GX = interp_rows(gx, rows, xs)
    # xonly: horizontal derivative only -- horizontal stripes of the band then
    # give no evidence (for steep walls)
    GY = np.zeros_like(GX) if xonly else interp_rows(gy, rows, xs)
    nrm = np.sqrt(1 + dxs ** 2)
    nx, ny = sgn / nrm, sgn * dxs / nrm
    D = GX[:, :, None] * nx[None, None, :] + GY[:, :, None] * ny[None, None, :]
    E = np.minimum(D, cap)
    if in_ok is not None:
        ok = in_ok(rows, xs)
        E[~ok] = np.minimum(E[~ok], 0) - cap
    if blind is not None:
        E[np.asarray(blind)] = 0.0                        # wall hidden: no evidence
    shift = np.round(dxs / step).astype(int)
    kk = np.arange(K)
    pen = mu * np.abs(kk[:, None] - kk[None, :])
    score = np.full((S, K), -np.inf)
    s0 = int(round((x0 - xs[0]) / step))
    score[s0, :] = -2 * mu * np.abs(dxs - slope0) / step
    back = np.zeros((rows.size, S, K), np.int16)
    src_all = np.arange(S)
    for r in range(rows.size):
        new = np.empty((S, K))
        for k in range(K):
            src = src_all - shift[k]
            okk = (src >= 0) & (src < S)
            cand = score[np.clip(src, 0, S - 1)] - pen[k][None, :]
            cand[~okk] = -np.inf
            a = np.argmax(cand, axis=1)
            new[:, k] = cand[src_all, a] + E[r, :, k]
            back[r, :, k] = a
        score = new
    s, k = np.unravel_index(np.argmax(score), score.shape)
    ps = np.zeros(rows.size, int)
    pk = np.zeros(rows.size, int)
    for r in range(rows.size - 1, -1, -1):
        ps[r], pk[r] = s, k
        k_old = back[r, s, k]
        s = s - shift[k]
        k = k_old
    return rows, xs[ps], D[np.arange(rows.size), ps, pk]


class Continuation:
    """Smooth (quadratic, curvature-clamped) continuation of a wall x(y) from
    its most recent accepted rows."""

    def __init__(self, ys, xs, n_fit=25, max_curv=0.01):
        self.y, self.x = list(ys), list(xs)
        self.n, self.c = n_fit, max_curv

    def add(self, y, x):
        self.y.append(y)
        self.x.append(x)

    def reset(self, ys, xs):
        self.y, self.x = list(ys), list(xs)

    def __call__(self, y):
        yy, xx = np.array(self.y, float), np.array(self.x, float)
        sel = np.argsort(yy)[:self.n]                   # rows closest to the top
        yy, xx = yy[sel], xx[sel]
        if yy.size == 0:
            return np.nan
        y0 = yy.min()
        if yy.size >= 6 and np.ptp(yy) >= 5:
            c2 = float(np.clip(np.polyfit(yy - y0, xx, 2)[0], -self.c, self.c))
            c1, c0 = np.polyfit(yy - y0, xx - c2 * (yy - y0) ** 2, 1)
        elif yy.size >= 2 and np.ptp(yy) > 0:
            c2 = 0.0
            c1, c0 = np.polyfit(yy - y0, xx, 1)
        else:
            c2, c1, c0 = 0.0, 0.0, float(xx[0])
        return float(c0 + c1 * (y - y0) + c2 * (y - y0) ** 2)


def fill_wall(rows, x, meas, x_below, y_below, tol=3.0, max_gap=6, skip=None):
    """
    Wall x(y) above an anchor from DP-tracked positions.  Going up row by row,
    a tracked position is accepted only if it has a clear edge (`meas`) AND
    agrees within `tol` px with the smooth continuation of the rows accepted
    so far; short gaps are bridged, and after `max_gap` rejected rows the
    continuation is used up to the surface.  `skip` rows (wall hidden) take
    the continuation without counting as misses.  Returns (x, not-measured flags).
    """
    order = np.argsort(-rows)                        # from the anchor upward
    ry, rx, rm = rows[order], x[order].astype(float), meas[order]
    rs = np.zeros(ry.size, bool) if skip is None else np.asarray(skip)[order]
    cont = Continuation(y_below, x_below)
    out = np.empty(ry.size)
    fl = np.ones(ry.size, bool)
    miss, alive = 0, True
    for i, (y, xv, m) in enumerate(zip(ry, rx, rm)):
        pred = cont(y)
        if rs[i]:                                    # hidden (e.g. by a bubble):
            out[i] = pred                            # continuation, not a miss
            continue
        if alive and m and abs(xv - pred) <= tol:
            out[i] = xv
            fl[i] = False
            miss = 0
            cont.add(y, xv)
        else:
            out[i] = pred
            miss += 1
            if miss > max_gap:
                alive = False
    acc = np.flatnonzero(~fl)
    for a, b in zip(acc[:-1], acc[1:]):              # bridge accepted gaps linearly
        if b - a > 1:
            out[a + 1:b] = np.linspace(out[a], out[b], b - a + 1)[1:-1]
    res = np.empty_like(out)
    res[order] = out
    f2 = np.empty_like(fl)
    f2[order] = fl
    return res, f2


def extend_air(air, R, gx, gy, cut, p):
    """Where the air region is closed below the free surface (cavity walls
    hidden by a light stripe of the meniscus band), trace each wall upward from
    its first clean rows; keep only rows with a clear wall edge that agrees
    with the wall below and extrapolate the rest smoothly up to the surface
    (flagged as not measured).  Returns (air, flags[2, H])."""
    H = air.shape[0]
    flags = np.zeros((2, H), bool)
    xl, xr = row_edges(air)
    ys = np.where(~np.isnan(xl))[0]
    if ys.size == 0 or ys[0] <= cut + 3:              # walls reach the surface
        return air, flags
    y_top, y_bot = int(ys[0]), int(ys[-1])
    anchors = [side_anchor(xw, y_top, y_bot, cut) for xw in (xl, xr)]
    anchors = [a if a is not None and a > cut + 2 else None for a in anchors]
    if all(a is None for a in anchors):
        return air, flags
    anchors = [a if a is not None else cut for a in anchors]
    walls = [xl.copy(), xr.copy()]
    for side, (xw, ya) in enumerate(zip((xl, xr), anchors)):
        if ya <= cut:
            continue
        sgn_in = 1 if side == 0 else -1

        def in_ok(rows, xs, s=sgn_in):
            return interp_rows(R, rows, xs + 3 * s) < p.t_air_hi
        rows, xp, Dp = track_wall(gx, gy, side, ya, float(xw[ya]), cut,
                                  slope0=wall_slope(xw, ya), in_ok=in_ok)
        inside = np.array([interp_rows(R, np.array([r]), np.array([v + 3 * sgn_in]))[0, 0]
                           for r, v in zip(rows, xp)])
        meas = (Dp >= p.g_meas) & (inside < p.t_air_hi)
        yb = np.arange(ya, min(ya + 30, H))
        yb = yb[~np.isnan(xw[yb])]
        xn, fl = fill_wall(rows, xp, meas, xw[yb], yb)
        walls[side][rows] = xn
        flags[side, rows] = fl
    ya_max = max(anchors)
    out = air.copy()
    out[:ya_max] = 0
    for r in range(cut, ya_max):
        a, b = walls[0][r], walls[1][r]
        if np.isnan(a) or np.isnan(b):
            continue
        a, b = int(round(a)), int(round(b))
        if b > a:
            out[r, max(a, 0):b + 1] = 255
    return out, flags


def path_derivative(gx, gy, side, rows, xs):
    """Outward directional derivative across a wall path x(y) (consecutive
    rows), per row, in the input order."""
    o = np.argsort(rows)
    r, x = rows[o].astype(float), xs[o].astype(float)
    dx = np.gradient(x) if x.size > 1 else np.zeros_like(x)
    sg = -1.0 if side == 0 else 1.0
    nrm = np.sqrt(1 + dx ** 2)
    gxv = map_coordinates(gx, [r, x], order=1, mode="nearest")
    gyv = map_coordinates(gy, [r, x], order=1, mode="nearest")
    D = np.empty_like(x)
    D[o] = (gxv * sg - gyv * sg * dx) / nrm
    return D


def path_strength(gx, gy, side, rows, xs, cap=0.05, xonly=False):
    """Mean outward directional derivative (dark inside -> bright outside,
    saturated at +-cap) along a wall path x(y) given on consecutive rows."""
    if rows.size < 2:
        return -cap
    o = np.argsort(rows)
    r, x = rows[o], xs[o].astype(float)
    dx = np.gradient(x)                                   # dx/dy
    sg = -1.0 if side == 0 else 1.0
    nrm = np.sqrt(1 + dx ** 2)
    gxv = map_coordinates(gx, [r.astype(float), x], order=1, mode="nearest")
    gyv = 0.0 if xonly else map_coordinates(gy, [r.astype(float), x], order=1, mode="nearest")
    D = (gxv * sg - gyv * sg * dx) / nrm
    return float(np.clip(D, -cap, cap).mean())


def retrace_top(air, flags, R, gx, gy, cut, zone_bottom, p, sats=(), tol=0.003):
    """
    Top of the meniscus band (the `top_rows` rows below the surface): here a
    dark stripe of the band can join the air region outside the crater, so
    the segmented wall may step sideways and run up to the surface as an 'L',
    a shelf or a hook, and a small bubble sitting on the wall can hide it.
    Per side the wall is re-traced up to the surface from the row `top_rows`
    below it (or from below a bubble reaching up there) by the 2nd-order DP
    wall tracker: a smooth path that follows the strongest dark->bright edge
    (no evidence inside a bubble).  It replaces the segmented wall unless the
    segmented one has clearly more edge evidence (a genuinely sharp rim).
    Rows without an edge on the re-traced wall are flagged not measured.
    """
    H, W = air.shape
    xl, xr = row_edges(air)
    ys = np.where(~np.isnan(xl))[0]
    if ys.size < 12 or ys[0] > cut + 3:
        return air, flags
    y_bot = min(int(ys[-1]), zone_bottom)
    walls = [xl.copy(), xr.copy()]
    changed = False
    for side in (0, 1):
        xw = walls[side]
        # anchor: first row at or below `top_rows` from which the wall is clean
        # (no step > 3 px over the next 20 rows: below any bay / shelf)
        ya = None
        # start below the lowest sideways step (> 5 px/row) of the wall in the
        # top part of the band (a bay / shelf from a stripe)
        y0 = min(cut + p.top_rows, y_bot - 5)
        zone = np.arange(cut, min(y_bot - 22, cut + p.top_rows + 40))
        if zone.size:
            st_ = np.abs(xw[zone + 1] - xw[zone])
            kk = zone[np.nan_to_num(st_, nan=0) > 5]
            if kk.size:
                y0 = max(y0, int(kk.max()) + 2)
        for y in range(y0, max(y_bot - 22, cut + 6)):
            seg = xw[y:y + 21]                       # 20 clean rows below the anchor
            if not np.isnan(seg).any() and np.abs(np.diff(seg)).max() <= 3:
                ya = y
                break
        if ya is None:
            continue
        # rows in which the segmented wall runs along a surface bubble
        near = np.zeros(H, bool)
        for (cx, cy, r) in sats:
            for y in range(max(int(cy - r - 6), cut), min(int(cy + r + 6), y_bot) + 1):
                if not np.isnan(xw[y]) and np.hypot(xw[y] - cx, y - cy) < r + 5:
                    near[max(y - 2, 0):y + 3] = True
        nr = np.flatnonzero(near)
        if nr.size and nr.min() <= ya and nr.max() + 1 > ya:
            ya = min(int(nr.max()) + 1, y_bot - 5)
        if ya - cut < 6 or np.isnan(xw[ya]):
            continue
        # a row tracker only follows steep walls; a late, flat crater's walls
        # run nearly horizontally and are left as segmented
        sl = np.abs(np.diff(xw[ya:ya + 11]))
        if np.isnan(sl).any() or np.median(sl) > 2.5:
            continue
        # the oil/air wall is the FIRST dark->bright edge met going outward
        # from the crater: per row, the wall may not lie beyond the first
        # bright ridge (a rise followed by a drop of > dip) reached from inside
        # the crater -- beyond it lie the oil's dark rim and the oil/water edge
        out_dir = 1 if side == 1 else -1
        lim = np.full(H, np.inf if side == 1 else -np.inf)
        for y in range(cut, ya + 1):
            xa = xw[y] if not np.isnan(xw[y]) else xw[ya]
            x_s = int(round(xa - out_dir * 12))
            prof = R[y, x_s::out_dir] if out_dir == 1 else R[y, x_s::-1]
            if prof.size < 3:
                continue
            run = np.maximum.accumulate(prof)
            drop = np.flatnonzero(run - prof > p.dip_tol_wall)
            if drop.size:
                k = int(np.argmax(prof[:drop[0]]))            # the ridge
                lim[y] = x_s + out_dir * k

        def in_ok(rows, xs, s=out_dir):
            return (xs[None, :] * s) <= (lim[rows][:, None] * s)
        rows = np.arange(ya - 1, cut - 1, -1)
        blind = near[rows]
        rows, xp, Dp = track_wall(gx, gy, side, ya, float(xw[ya]), cut,
                                  slope0=wall_slope(xw, ya), in_ok=in_ok, win=90,
                                  max_slope=4.0, mu=0.02, blind=blind, xonly=True)
        if rows.size == 0:
            continue
        use = ~blind
        if use.sum() < 3:
            use = np.ones(rows.size, bool)
        e_new = path_strength(gx, gy, side, rows[use], xp[use], xonly=True)
        old_x = xw[rows]
        if np.isnan(old_x).any():
            e_old = -1.0
        else:
            e_old = path_strength(gx, gy, side, rows[use], old_x[use], xonly=True)
        Dn = path_derivative(gx, gy, side, rows, xp)      # across the new wall
        seen = float(((Dn >= p.g_meas) & ~blind).sum()) / max(int((~blind).sum()), 1)
        if e_new >= e_old - tol and (seen >= 0.5 or e_new > e_old + 0.005):
            xw[rows] = xp
            flags[side, rows] = (Dn < p.g_meas) | blind
            changed = True
    if not changed:
        return air, flags
    out = air.copy()
    for y in range(int(ys[0]), y_bot):
        a, b = walls[0][y], walls[1][y]
        out[y] = 0
        if not (np.isnan(a) or np.isnan(b)) and b > a:
            out[y, max(int(round(a)), 0):min(int(round(b)), W - 1) + 1] = 255
    return out, flags


def _dir_deriv(gx, gy, x, y, sgo):
    """Derivative across a rim path y(x) (x stepping outward by sgo), positive
    for dark air above -> brighter liquid below."""
    dy = np.gradient(y, axis=-1) * sgo if y.shape[-1] > 1 else np.zeros_like(y)
    nrm = np.sqrt(1 + dy ** 2)
    gxv = map_coordinates(gx, [y.ravel(), np.broadcast_to(x, y.shape).ravel()],
                          order=1, mode="nearest").reshape(y.shape)
    gyv = map_coordinates(gy, [y.ravel(), np.broadcast_to(x, y.shape).ravel()],
                          order=1, mode="nearest").reshape(y.shape)
    return (-gxv * dy + gyv) / nrm


def retrace_rim_shallow(air, flags, R, gx, gy, cut, zone_bottom, p, tol=0.003, cap=0.05):
    """
    Shallow crater walls near the surface (late collapse: a wide crater whose
    wall, where it leaves the bottom, is flatter than --shallow-slope).
    There the horizontal stripes of the meniscus band look locally just like
    the wall, so an edge tracker (and the segmentation) follows them into
    steps, boxes and shelves.  Instead, per side, the rim is modelled as the
    segmented crater bottom out to an anchor column xa, then a smooth curve
    y(u) = y_a + a1 u - k u^2 (u = px outward from xa) up to the free surface.
    xa, a1 and k are searched on a grid; the path with the strongest mean edge
    evidence along its normal (dark air above -> brighter liquid below, never
    beyond the first bright ridge below the crater), measured over the same
    stretch from a fixed inner column for every candidate, is taken.  It
    replaces the segmented rim unless that has clearly more evidence.
    """
    from scipy.ndimage import median_filter
    H, W = air.shape
    m = air > 0
    has = m.any(axis=0)
    cols = np.flatnonzero(has)
    if cols.size < 30:
        return air, flags
    yb = np.where(has, H - 1 - np.argmax(m[::-1], axis=0), -1).astype(float)
    ybs = yb.copy()
    ybs[cols] = median_filter(yb[cols], size=7, mode="nearest")
    c0, c1 = int(cols[0]), int(cols[-1])
    cx = int(round(np.median(cols[yb[cols] >= yb[cols].max() - 3])))
    depth = yb[cx] - cut
    if depth < 15:
        return air, flags
    out = air.copy()
    changed = False
    for side in (0, 1):
        sgo = -1 if side == 0 else 1
        edge = c0 if side == 0 else c1
        span = abs(edge - cx)
        if span < 20:
            continue
        x_in = int(cx + sgo * 0.5 * span)
        # the wall where it leaves the bottom must be shallow
        xx = x_in + sgo * np.arange(0, 16)
        yy = ybs[xx]
        if (yy < 0).any() or abs(np.polyfit(np.arange(16), yy, 1)[0]) > p.shallow_slope:
            continue
        # first bright ridge going down from inside the crater, per column
        lim = np.full(W, np.inf)
        xs_all = np.arange(x_in, edge + sgo * 80, sgo)
        xs_all = xs_all[(xs_all >= 0) & (xs_all < W)]
        for x in xs_all:
            if yb[x] < cut + 12:
                continue
            y_s = int(yb[x] - 12)
            prof = R[y_s:zone_bottom, x]
            if prof.size < 3:
                continue
            run_ = np.maximum.accumulate(prof)
            dr = np.flatnonzero(run_ - prof > p.dip_tol_wall)
            if dr.size:
                lim[x] = y_s + int(np.argmax(prof[:dr[0]]))
        # evidence along the segmented bottom from x_in outward (cumulative)
        nb = abs(edge - x_in) + 1
        xb = x_in + sgo * np.arange(nb)
        Eb = np.minimum(_dir_deriv(gx, gy, xb.astype(float), np.maximum(ybs[xb], cut), sgo), cap)
        cumb = np.concatenate([[0.0], np.cumsum(Eb)])
        best = None
        a1s = np.arange(-0.9, 0.31, 0.15)                    # dy/du (up = negative)
        ks = np.linspace(-0.01, 0.06, 29)
        A1, K = np.meshgrid(a1s, ks, indexing="ij")
        A1, K = A1.ravel(), K.ravel()
        for ia in range(3, nb - 2, 3):
            xa = int(xb[ia])
            y_a = float(max(ybs[xa], cut + 2))
            us = np.arange(0, abs(edge - xa) + 80)
            xs = xa + sgo * us
            ok = (xs >= 0) & (xs < W)
            us, xs = us[ok], xs[ok]
            if us.size < 6:
                continue
            Y = y_a + A1[:, None] * us[None, :] - K[:, None] * us[None, :] ** 2
            reach = Y <= cut + 1
            end = np.where(reach.any(axis=1), np.argmax(reach, axis=1), -1)
            valid = end >= 4
            if not valid.any():
                continue
            Yc = np.clip(Y, cut, H - 1)
            D = _dir_deriv(gx, gy, xs.astype(float), Yc, sgo)
            E = np.minimum(D, cap)
            E[Yc > lim[xs][None, :]] = -cap
            upto = np.arange(us.size)[None, :] <= end[:, None]
            sumE = np.where(upto, E, 0).sum(axis=1)
            n_ = upto.sum(axis=1)
            score = (cumb[ia] + sumE) / (ia + n_)
            score[~valid] = -np.inf
            j = int(np.argmax(score))
            if best is None or score[j] > best[0]:
                e_ = int(end[j]) + 1
                best = (float(score[j]), ia, xs[:e_].astype(float), Yc[j, :e_], D[j, :e_])
        if best is None:
            continue
        e_new, ia, x_n, y_n, D_n = best
        # evidence of the segmented wall over the same stretch
        xo = np.concatenate([xb[:ia], x_n.astype(int)])
        yo = yb[xo]
        vv = yo >= cut
        if vv.sum() < 5 or not vv[ia:].any():
            e_old = -1.0
        else:
            e_old = float(np.minimum(_dir_deriv(gx, gy, xo[vv].astype(float), yo[vv], sgo), cap).mean())
        seen = float((D_n >= p.g_meas).mean())
        if not (e_new > 0 and e_new >= p.rim_keep * e_old - tol and seen >= 0.2):
            continue
        x_end = int(x_n[-1])
        for x, y, d in zip(x_n.astype(int), y_n, D_n):
            out[cut:zone_bottom, x] = 0
            out[cut:int(round(y)) + 1, x] = 255
            r_ = int(round(y))
            if cut <= r_ < H:
                flags[side, r_] = d < p.g_meas
        far = np.arange(x_end + sgo, (-1 if side == 0 else W), sgo)
        if far.size:
            out[cut:zone_bottom, far] = 0
        changed = True
    if not changed:
        return air, flags
    return fill_rows(out), flags


def wall_slope(x, y0, n=10):
    """Per-row slope of a wall going UP (x(y-1) - x(y)) from rows y0..y0+n."""
    yy = np.arange(y0, min(y0 + n, x.size))
    xx = x[yy]
    ok = ~np.isnan(xx)
    if ok.sum() < 3:
        return 0.0
    return float(-np.polyfit(yy[ok], xx[ok], 1)[0])


def track_outer(lower, air, air_flags, R, gx, cut, p, s_out=1.5, s_in=25, tol=4.0):
    """
    Outer (water/oil) outline inside the free-surface band, row by row upward
    from the top of the reliable lower object.  Candidate in each row: the
    first pixel (searched from at most `s_out` px outside the previous edge --
    no leaks into surface shadows -- inward up to the air wall) that is darker
    than (1 - t_out) x the LOCAL water level just outside (dark rim), or
    brighter than (1 + t_lens) x it (inside the band the oil shell acts as a
    lens and looks brighter than water).
      * candidate at the air wall -> no visible oil: the outline IS the air
        wall (water/air contact); once reached it is kept up to the surface
        (a dark ring further out is a separate satellite drop)
      * candidate agreeing (+-tol) with the smooth continuation of the outline
        below -> accepted (measured if there is a real intensity step)
      * otherwise the continuation is used (not measured), never inside air.
    Returns (outer mask, flags[2, H]).
    """
    H, W = lower.shape
    flags = np.zeros((2, H), bool)
    xl, xr = row_edges(lower)
    ys = np.where(~np.isnan(xl))[0]
    if ys.size == 0:
        return lower, flags
    ya = int(ys[0])
    if ya <= cut + 2:
        return lower, flags
    axl, axr = row_edges(air)
    rows = np.arange(ya - 1, cut - 1, -1)
    thr = 1.0 - p.t_out
    yb = ys[:25]
    walls = []
    for side in (0, 1):
        xw = xl if side == 0 else xr
        aw = axl if side == 0 else axr
        sg = -1 if side == 0 else 1                      # outward direction
        cont = Continuation(yb, xw[yb])
        cur = float(xw[ya])
        path = np.zeros(rows.size)
        fl = np.zeros(rows.size, bool)
        contact = 0
        for k, y in enumerate(rows):
            row = R[y]
            has_air = not np.isnan(aw[y])
            pred = cont(y)
            if side == 0:
                a = int(max(np.floor(cur - s_out), 0))
                b = int(aw[y]) if has_air else int(min(cur + s_in, W - 1))
                seg = row[max(a - 40, 0):max(a - 6, 1)]
            else:
                b = int(min(np.ceil(cur + s_out), W - 1))
                a = int(aw[y]) if has_air else int(max(cur - s_in, 0))
                seg = row[min(b + 6, W - 1):min(b + 40, W)]
            wat = float(np.clip(np.median(seg), 0.8, 1.4)) if seg.size > 3 else 1.0
            win = row[a:b + 1] if b >= a else np.array([])
            hit = np.flatnonzero((win < thr * wat) | (win > (1.0 + p.t_lens) * wat))
            cand = None
            if hit.size:
                cand = float(a + (hit[0] if side == 0 else hit[-1]))
            if contact >= 3 and has_air:
                cand = float(aw[y])
            x, meas = None, False
            if cand is not None and has_air and -sg * (aw[y] - cand) <= 2.0:
                contact += 1                                     # water/air contact
                x = float(aw[y])
                meas = not air_flags[side, y]
                if abs(x - pred) > tol:
                    cont.reset([y], [x])
                else:
                    cont.add(y, x)
            elif cand is not None and abs(cand - pred) <= tol:
                contact = 0
                j0, j1 = int(cand) - 3, int(cand) + 4
                x = cand
                meas = float(np.abs(gx[y, max(j0, 0):j1]).max()) >= p.g_meas
                cont.add(y, x)
            if x is None:
                x = pred
                if has_air and sg * (aw[y] - x) > 0:             # never inside the air
                    x = float(aw[y])
            cur = x
            path[k], fl[k] = x, not meas
        flags[side, rows] = fl
        walls.append(path)
    out = lower.copy()
    for r, a, b in zip(rows, walls[0], walls[1]):
        a, b = int(round(a)), int(round(b))
        if b > a:
            out[r, max(a, 0):b + 1] = 255
    return out, flags


# --------------------------------------------------------------------------- #
#  Contours and sub-pixel refinement
# --------------------------------------------------------------------------- #
def open_contour(mask, cut, tol=0.5):
    """
    The interface as ONE continuous, ordered curve: the outer contour of the
    mask without its points on the free-surface cut line (the artificial
    'lid'); if the lid is interrupted by small dips, only the longest remaining
    piece (the interface itself) is kept.  Ordered from the end with the
    smaller x.  If the mask does not touch the cut line (closed bubble or
    drop), the closed contour is returned unchanged.
    Returns (curve (N,2) int, raw closed contour, is_closed).
    """
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not cnts:
        return None, None, False
    c = max(cnts, key=cv2.contourArea)
    pts = c[:, 0, :]
    on = pts[:, 1] <= cut + tol
    if not on.any() or on.all():
        return pts, c, True
    k = int(np.flatnonzero(on)[-1]) + 1
    pts, on = np.roll(pts, -k, 0), np.roll(on, -k)       # starts right after the lid
    # pieces between lid points; the longest one is the interface
    best, best_rng, start = 0, None, None
    for j, v in enumerate(np.append(on, True)):
        if not v and start is None:
            start = j
        elif v and start is not None:
            if j - start > best:
                best, best_rng = j - start, (start, j)
            start = None
    a, b = best_rng
    curve = pts[a:b]
    # a lid can also run 1-3 rows below the cut (thin bright line at the
    # surface): trim such rows off both ends, then continue the curve straight
    # up to the cut line
    near = curve[:, 1] <= cut + 3
    if near.all():
        return None, c, False
    i0 = int(np.argmax(~near))
    i1 = len(curve) - int(np.argmax(~near[::-1]))
    curve = curve[i0:i1]
    ends = [curve[:1].copy(), curve[-1:].copy()]
    for e in ends:
        e[0, 1] = int(np.floor(cut))
    curve = np.vstack([ends[0], curve, ends[1]])
    if curve[0, 0] > curve[-1, 0]:
        curve = curve[::-1]
    return curve, c, False


def resample_curve(P, closed=False, sigma=2.0, step=1.0):
    """Smooth an ordered integer contour and resample it at ~`step` px."""
    P = P.astype(np.float64)
    if len(P) < 5:
        return P
    mode = 'wrap' if closed else 'nearest'
    Ps = np.stack([gaussian_filter1d(P[:, k], sigma, mode=mode) for k in (0, 1)], 1)
    if not closed:                                   # ends stay on the cut line
        Ps[0], Ps[-1] = P[0], P[-1]
    Q = np.vstack([Ps, Ps[:1]]) if closed else Ps
    s = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(Q, axis=0), axis=1))])
    L = s[-1]
    if L < 2 * step:
        return Ps
    n = int(np.floor(L / step)) + (0 if closed else 1)
    t = np.linspace(0, L - L / n if closed else L, n)
    return np.stack([np.interp(t, s, Q[:, 0]), np.interp(t, s, Q[:, 1])], 1)


def curve_normals(P, closed=False, k=3):
    n = len(P)
    idx = np.arange(n)
    if closed:
        fwd, bwd = P[(idx + k) % n], P[(idx - k) % n]
    else:
        fwd, bwd = P[np.minimum(idx + k, n - 1)], P[np.maximum(idx - k, 0)]
    t = fwd - bwd
    t /= np.maximum(np.linalg.norm(t, axis=1, keepdims=True), 1e-9)
    return np.stack([-t[:, 1], t[:, 0]], 1)


def orient_outward(P, nrm, mask, d=3.0):
    """Flip the normals so that they point out of the mask (majority vote)."""
    h, w = mask.shape

    def outside(q):
        q = np.round(q).astype(int)
        q[:, 0] = q[:, 0].clip(0, w - 1)
        q[:, 1] = q[:, 1].clip(0, h - 1)
        return (mask[q[:, 1], q[:, 0]] == 0).mean()
    return nrm if outside(P + d * nrm) >= outside(P - d * nrm) else -nrm


def dp_edge(P, nrm, img, win_in, win_out, step=0.25, lam=0.02, max_jump=1.0,
            dip_tol=None, rise_tol=None, absolute=None):
    """
    Optimal edge offsets s_i along the normals of an ordered curve (Viterbi):
    maximise  sum_i dR/dn(P_i + s_i n_i)  -  lam * sum_i |s_i - s_{i-1}|
    with |s_i - s_{i-1}| <= max_jump.  dR/dn > 0 = dark inside, bright outside.
      dip_tol  : an outward offset is only allowed if the profile from the
                 start point to it never drops more than dip_tol below its
                 running maximum (may cross a gray zone, never a bright ridge
                 followed by a dark valley = another interface)
      rise_tol : an inward offset is only allowed if the profile from the
                 start point to it never rises more than rise_tol above its
                 running minimum (may descend a soft ramp into a dark rim,
                 never cross the rim into the next, brighter region)
      absolute : boolean per point -> use |dR/dn| (either polarity)
    Returns (offsets with parabolic sub-sample refinement, dR/dn there).
    """
    offs = np.arange(-win_in, win_out + step / 2, step)
    X = P[:, 0:1] + nrm[:, 0:1] * offs
    Y = P[:, 1:2] + nrm[:, 1:2] * offs
    prof = map_coordinates(img, [Y, X], order=1, mode='nearest')
    D = np.gradient(prof, step, axis=1)
    E = D.copy()
    if absolute is not None and absolute.any():
        E[absolute] = np.abs(D[absolute])
    if dip_tol is not None:
        j0 = int(np.argmin(np.abs(offs)))
        seg = prof[:, j0:]
        dd = np.maximum.accumulate(np.maximum.accumulate(seg, axis=1) - seg, axis=1)
        bad = np.zeros_like(E, bool)
        bad[:, j0 + 1:] = dd[:, :-1] > dip_tol
        E[bad] = -1.0
    if rise_tol is not None:
        j0 = int(np.argmin(np.abs(offs)))
        seg = prof[:, j0::-1]                       # from the start point inward
        rr = np.maximum.accumulate(seg - np.minimum.accumulate(seg, axis=1), axis=1)
        bad = np.zeros_like(E, bool)
        bad[:, :j0] = (rr[:, 1:] > rise_tol)[:, ::-1]
        E[bad] = -1.0
    n, S = E.shape
    J = int(round(max_jump / step))
    pen = lam * np.abs(np.arange(-J, J + 1)) * step
    score = E[0].copy()
    back = np.zeros((n, S), np.int32)
    ar = np.arange(S)
    for i in range(1, n):
        best = np.full(S, -np.inf)
        arg = np.zeros(S, np.int32)
        for kk, dj in enumerate(range(-J, J + 1)):
            src = ar - dj
            ok = (src >= 0) & (src < S)
            cand = np.full(S, -np.inf)
            cand[ok] = score[src[ok]] - pen[kk]
            better = cand > best
            best[better] = cand[better]
            arg[better] = src[better]
        score = best + E[i]
        back[i] = arg
    j = np.zeros(n, np.int32)
    j[-1] = int(np.argmax(score))
    for i in range(n - 1, 0, -1):
        j[i - 1] = back[i, j[i]]
    # sub-sample position: local maximum of the edge response next to the
    # DP choice (+-2 samples), then a parabola through it and its neighbours
    ii = np.arange(n)
    cand = np.clip(j[:, None] + np.arange(-2, 3)[None, :], 0, S - 1)
    jl = cand[ii, np.argmax(E[ii[:, None], cand], axis=1)]
    jj = np.clip(jl, 1, S - 2)
    a, b, c = E[ii, jj - 1], E[ii, jj], E[ii, jj + 1]
    den = a - 2 * b + c
    ok = (den < 0) & (jl == jj)
    delta = np.zeros(n)
    delta[ok] = np.clip(0.5 * (a[ok] - c[ok]) / den[ok], -0.5, 0.5)
    s = offs[jj] + delta * step
    return s, D[ii, jj]


def refine_interface(mask, img, cut, win_in, win_out, lam, dip_tol=None, rise_tol=None,
                     abs_above=None):
    """Contour of a mask -> smooth, resampled -> optimal sub-pixel edge along
    the normals.  Returns (curve (N,2) float, strength (N,), closed, raw contour)."""
    oc, raw, closed = open_contour(mask, cut)
    if oc is None or len(oc) < 8:
        return None, None, False, raw
    P = resample_curve(oc, closed)
    nrm = orient_outward(P, curve_normals(P, closed), mask)
    absolute = None if abs_above is None else P[:, 1] < abs_above
    s, st = dp_edge(P, nrm, img, win_in, win_out, lam=lam, dip_tol=dip_tol, rise_tol=rise_tol,
                    absolute=absolute)
    Q = P + nrm * s[:, None]
    Q[:, 1] = np.maximum(Q[:, 1], cut)
    if not closed:
        Q[0, 1] = Q[-1, 1] = cut                     # ends on the free surface
    if absolute is not None:
        st = np.where(absolute, np.abs(st), st)
    return Q, st, closed, raw


def remove_folds(Q, d=2.5, max_len=90, min_gap=6, d_spike=6.0, spike_ratio=4.0):
    """Cut out narrow spikes / folds of an ordered curve: wherever the curve
    comes back to within `d` px of a point it passed at most `max_len` points
    earlier (and at least `min_gap` later), the excursion in between is
    removed; likewise a tall narrow spike (back within `d_spike` px after an
    excursion > spike_ratio * 2 * d_spike px long).  Such folds are not
    interface features but the sub-pixel refinement pushing the points of a
    sharp corner out along fanning normals."""
    if Q is None or len(Q) < 3 * min_gap:
        return Q
    from scipy.spatial import cKDTree
    P = Q.astype(np.float64)
    tree = cKDTree(P)
    keep = np.ones(len(P), bool)
    i = 0
    n = len(P)
    arc = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))])
    while i < n:
        nb = [j for j in tree.query_ball_point(P[i], d) if i + min_gap <= j <= i + max_len]
        # a tall narrow spike: returns within d_spike px after an excursion
        # more than spike_ratio x longer
        nb += [j for j in tree.query_ball_point(P[i], d_spike)
               if i + min_gap <= j <= i + max_len and arc[j] - arc[i] > spike_ratio * 2 * d_spike]
        if nb:
            j = max(nb)
            keep[i + 1:j] = False
            i = j
        else:
            i += 1
    return P[keep]


def remove_loops(Q, max_loop=400):
    """Cut small self-intersection loops out of an ordered curve (they appear
    where the sub-pixel refinement moves the points of a sharp corner along
    crossing normals): wherever segment i crosses a later segment j (within
    `max_loop` points), the points between are replaced by the crossing."""
    if Q is None or len(Q) < 8:
        return Q
    P = Q.astype(np.float64)
    out = []
    i, n = 0, len(P)
    while i < n - 1:
        a, b = P[i], P[i + 1]
        j1 = min(n - 1, i + max_loop)
        if j1 > i + 2:
            c, d = P[i + 2:j1], P[i + 3:j1 + 1]
            r = b - a
            sv = d - c
            den = r[0] * sv[:, 1] - r[1] * sv[:, 0]
            qp = c - a
            with np.errstate(divide="ignore", invalid="ignore"):
                t = (qp[:, 0] * sv[:, 1] - qp[:, 1] * sv[:, 0]) / den
                u = (qp[:, 0] * r[1] - qp[:, 1] * r[0]) / den
            hit = np.flatnonzero((np.abs(den) > 1e-12) & (t >= 0) & (t <= 1) & (u >= 0) & (u <= 1))
            if hit.size:
                k = int(hit[-1])                     # the largest loop starting here
                out.append(a)
                out.append(a + t[k] * r)
                i = i + 2 + k + 1                    # continue from the end of segment j
                continue
        out.append(a)
        i += 1
    out.append(P[-1])
    return np.array(out)


def _resample_flags(Q_old, f_old, Q_new):
    """Carry per-point flags from one version of a curve to another (nearest point)."""
    from scipy.spatial import cKDTree
    _, j = cKDTree(Q_old).query(Q_new)
    return f_old[j]


def smooth_ends(Q, meas, cut, zone_bottom, min_run=6, n_tan=12, rim_rows=30, max_ext=30):
    """
    Ends of an open interface inside the meniscus band that are not measured
    (the crater rim hidden where it meets the dark stripe under the surface)
    are replaced by a smooth continuation: a cubic Hermite curve from the last
    measured point, leaving it with the measured tangent, to the free-surface
    cut line -- where that tangent line meets the cut if it points upward,
    otherwise straight above the old end.  Keeps the flags 'not measured'.
    Returns (Q, meas).
    """
    if Q is None or len(Q) < 3 * n_tan:
        return Q, meas
    Q = Q.astype(np.float64).copy()
    meas = meas.copy()
    for end in (0, 1):
        q = Q if end == 0 else Q[::-1]
        m = (meas if end == 0 else meas[::-1]).copy()
        # a hook at the rim (the wall runs outward nearly horizontally, then
        # turns back inward/up within a few rows) is a stripe artifact: not
        # measured from the turning point to the end.  A gradually closing
        # bubble cap is not a hook.
        rim = int(np.argmax(q[:, 1] > cut + rim_rows)) if (q[:, 1] > cut + rim_rows).any() else 0
        if rim > 3:
            outw = (-q[:rim, 0]) if end == 0 else q[:rim, 0]
            j = int(np.argmax(outw))
            back = outw[j] - outw[:j + 1].min() if j > 0 else 0.0
            rise = q[j, 1] - q[:j + 1, 1].min() if j > 0 else 0.0
            if back > 3 and rise < 2.5 * back:
                m[:j] = False
        run = np.convolve(m.astype(int), np.ones(min_run, int), "valid") == min_run
        ok = np.flatnonzero(run)
        if ok.size == 0:
            continue
        k = int(ok[0])                                   # first measured stretch
        if k < 3 or q[:k, 1].max() >= zone_bottom or k > len(q) // 3:
            if end == 0:
                meas = m
            else:
                meas = m[::-1]
            continue
        P0 = q[k]
        t = q[k] - q[min(k + n_tan, len(q) - 1)]         # direction towards the end
        nt = np.linalg.norm(t)
        if nt < 1e-6:
            continue
        t /= nt
        sgo = -1.0 if end == 0 else 1.0                  # outward x direction
        if t[0] * sgo < -0.2 and t[1] > -0.7:            # nearly horizontal inward
            t = np.array([0.0, -1.0])                    # (shelf/hook): leave upward
        if t[1] < -0.25:                                 # heading up: meet the cut
            lam = (cut - P0[1]) / t[1]
            E = P0 + lam * t
            if abs(E[0] - P0[0]) > max_ext:              # shallow: do not run far out
                E[0] = P0[0] + np.sign(t[0]) * max_ext
        else:                                            # flat / downward: round off
            E = np.array([P0[0] + np.clip(q[0, 0] - P0[0], -max_ext, max_ext), float(cut)])
        L = max(np.linalg.norm(E - P0), 1.0)
        tE = np.array([0.0, -1.0]) if t[1] >= -0.25 else t
        n = max(int(np.ceil(L)), 4)
        u = np.linspace(0, 1, n + 1)[:, None]
        h00, h10 = 2 * u ** 3 - 3 * u ** 2 + 1, u ** 3 - 2 * u ** 2 + u
        h01, h11 = -2 * u ** 3 + 3 * u ** 2, u ** 3 - u ** 2
        H = h00 * P0 + h10 * L * t + h01 * E + h11 * L * tE
        H[:, 1] = np.maximum(H[:, 1], cut)
        new = np.vstack([H[::-1][:-1], q[k:]])           # end ... P0 ... rest
        nm = np.concatenate([np.zeros(n, bool), m[k:]])
        if end == 0:
            Q, meas = new, nm
        else:
            Q, meas = new[::-1], nm[::-1]
    return Q, meas


def smooth_band_shallow(Q, closed, zone_bottom, cut, sigma=10.0, win=15, slope=0.6):
    """
    Inside the meniscus band a shallow crater (late collapse) has a nearly
    horizontal bottom and rim, and the band's horizontal stripes turn it into
    a staircase of small steps (5-15 px) that are not in the interface.  Where
    the curve is inside the band and, over +-`win` px of arc, runs flatter
    than `slope` (dy/dx), it is smoothed more strongly (Gaussian `sigma` px
    along the arc); the weight is blended smoothly into the normal smoothing.
    The end points (on the free surface) are kept.
    """
    if Q is None or len(Q) < 4 * win:
        return Q
    Q = Q.astype(np.float64)
    mode = "wrap" if closed else "nearest"
    k = int(sigma * 4)
    if closed:
        ext = Q
    else:
        pre = 2 * Q[0] - Q[k:0:-1]
        post = 2 * Q[-1] - Q[-2:-k - 2:-1]
        ext = np.vstack([pre, Q, post])
    S = np.stack([gaussian_filter1d(ext[:, j], sigma, mode=mode) for j in (0, 1)], 1)
    S = S if closed else S[k:k + len(Q)]
    n = len(Q)
    idx = np.arange(n)
    a = Q[np.clip(idx + win, 0, n - 1)] - Q[np.clip(idx - win, 0, n - 1)]
    flat = np.abs(a[:, 1]) < slope * np.abs(a[:, 0]) + 1e-6
    w = (flat & (Q[:, 1] < zone_bottom) & (Q[:, 1] > cut + 3)).astype(float)
    w = np.clip(gaussian_filter1d(w, win / 2, mode=mode) * 1.5, 0, 1)
    if not closed:
        w[0] = w[-1] = 0.0
        taper = np.minimum(1.0, np.minimum(idx, n - 1 - idx) / max(win, 1))
        w *= taper
    return (1 - w[:, None]) * Q + w[:, None] * S


def smooth_curve(Q, closed=False, sigma=3.0, step=1.0):
    """Smooth an ordered sub-pixel curve along its arc length (Gaussian,
    `sigma` px) after resampling it to `step` px spacing.  Open curves keep
    their end points (odd reflection at the ends: the curve still ends on the
    free surface with its tangent there).  Removes pixel-scale wiggles
    (MJPEG noise, staircase of the segmentation); the bias on a curved
    interface is ~ sigma^2 / (2 R), i.e. < 0.1 px for R > 50 px."""
    if Q is None or len(Q) < 5 or sigma <= 0:
        return Q
    Q = Q.astype(np.float64)
    Qc = np.vstack([Q, Q[:1]]) if closed else Q
    d = np.linalg.norm(np.diff(Qc, axis=0), axis=1)
    s_ = np.concatenate([[0], np.cumsum(d)])
    L = s_[-1]
    if L < 4 * sigma:
        return Q
    n = max(int(round(L / step)), 5)
    t = np.linspace(0, L, n + 1) if not closed else np.linspace(0, L, n, endpoint=False)
    R_ = np.stack([np.interp(t, s_, Qc[:, 0]), np.interp(t, s_, Qc[:, 1])], 1)
    if closed:
        return np.stack([gaussian_filter1d(R_[:, k], sigma / step, mode="wrap") for k in (0, 1)], 1)
    k = min(int(4 * sigma / step), len(R_) - 1)
    pre = 2 * R_[0] - R_[k:0:-1]
    post = 2 * R_[-1] - R_[-2:-k - 2:-1]
    ext = np.vstack([pre, R_, post])
    sm = np.stack([gaussian_filter1d(ext[:, j], sigma / step, mode="nearest") for j in (0, 1)], 1)
    return sm[k:k + len(R_)]


def curve_strength(Q, closed, img, mask, absolute_above=None, reach=1.5, step=0.25):
    """Edge strength at each point of an ordered curve: the strongest
    derivative of `img` along the outward normal (dark inside -> bright
    outside > 0) within +-`reach` px of the point (after smoothing the curve
    may sit a fraction of a px off the exact maximum).  |derivative| above row
    `absolute_above` (lens-like oil in the band)."""
    nrm = orient_outward(Q, curve_normals(Q, closed), mask)
    offs = np.arange(-reach - step, reach + 1.5 * step, step)
    X = Q[:, 0:1] + nrm[:, 0:1] * offs
    Y = Q[:, 1:2] + nrm[:, 1:2] * offs
    prof = map_coordinates(img, [Y, X], order=1, mode="nearest")
    D = np.gradient(prof, step, axis=1)[:, 1:-1]
    if absolute_above is not None:
        ab = Q[:, 1] < absolute_above
        return np.where(ab, np.abs(D).max(axis=1), D.max(axis=1))
    return D.max(axis=1)


def merge_contact(outer, omeas, inner, imeas, contact_d=3.0, min_gap=12, min_run=4, end_d=8.0):
    """
    Where there is no oil between them (the oil has been pushed to the bottom
    and the crater wall is a water/air interface) the water/oil and oil/air
    interfaces are the SAME curve.  Outer points inside the inner curve or
    less than `contact_d` px outside it are 'contact'; short gaps (< min_gap
    points) between contact stretches and at the curve ends are closed, very
    short contact stretches (< min_run) inside oil are dropped.  Each contact
    stretch of the outer curve is then replaced by the corresponding piece of
    the inner curve itself, so both curves overlap exactly there; the corners
    where they separate are the triple points (water/oil/air).
    Returns (outer, outer_measured, contact flags per outer point).
    """
    from scipy.spatial import cKDTree
    poly = inner.astype(np.float32).reshape(-1, 1, 2)
    d = np.array([cv2.pointPolygonTest(poly, (float(x), float(y)), True) for x, y in outer])
    con = d > -contact_d
    n = len(con)

    def runs(b):
        idx = np.flatnonzero(np.diff(np.r_[0, b.astype(int), 0]))
        return list(zip(idx[::2], idx[1::2]))
    for a, b in runs(~con):                              # close short gaps
        if b - a < min_gap and (a > 0 and b < n):
            con[a:b] = True
    for a, b in runs(con):                               # drop tiny contacts
        if b - a < min_run and a > 0 and b < n:
            con[a:b] = False
    # an end stretch towards the free surface where the outer curve is only
    # extrapolated (not measured) and that starts at or next to the inner
    # curve: no oil is seen there -- the two are the same curve up to the end
    for end in (0, 1):
        idx = np.arange(n) if end == 0 else np.arange(n - 1, -1, -1)
        k = 0
        while k < n and not con[idx[k]] and not omeas[idx[k]]:
            k += 1
        if 0 < k < n and k < n // 3 and (con[idx[k]] or d[idx[k]] > -end_d):
            con[idx[:k + 1]] = True
    if not con.any():
        return outer, omeas, con
    tree = cKDTree(inner)
    parts, pm, pc = [], [], []
    for a, b in sorted(runs(con) + runs(~con)):
        if con[a]:
            _, ja = tree.query(outer[a])
            _, jb = tree.query(outer[b - 1])
            if a == 0:
                ja = 0                                   # both start on the surface
            if b == n:
                jb = len(inner) - 1
            if jb >= ja:
                seg, sm = inner[ja:jb + 1], imeas[ja:jb + 1]
            else:                                        # should not happen
                _, jj = tree.query(outer[a:b])
                seg, sm = inner[jj], imeas[jj]
            parts.append(seg); pm.append(sm); pc.append(np.ones(len(seg), bool))
        else:
            parts.append(outer[a:b]); pm.append(omeas[a:b]); pc.append(np.zeros(b - a, bool))
    return np.vstack(parts), np.concatenate(pm), np.concatenate(pc)


def row_flags_to_points(curve, flags):
    """Per curve point: True if the row flag of its side (left/right of the
    curve's middle) is set."""
    if flags is None or not flags.any():
        return np.zeros(len(curve), bool)
    xm = 0.5 * (curve[:, 0].min() + curve[:, 0].max())
    rows = np.clip(np.round(curve[:, 1]).astype(int), 0, flags.shape[1] - 1)
    side = (curve[:, 0] >= xm).astype(int)
    return flags[side, rows]


def curve_to_mask(curve, shape):
    """Filled polygon of a (closed or open-at-the-surface) curve."""
    m = np.zeros(shape, np.uint8)
    if curve is None or len(curve) < 3:
        return m
    q = np.round(curve * 16).astype(np.int32).reshape(-1, 1, 2)
    cv2.fillPoly(m, [q], 255, cv2.LINE_8, shift=4)
    return m


def curve_row_profile(curve):
    """Sub-pixel wall positions per integer row from an ordered curve:
    returns y, x_left, x_right (leftmost / rightmost crossing of the row)."""
    if curve is None or len(curve) < 2:
        return np.array([]), np.array([]), np.array([])
    x, y = curve[:, 0], curve[:, 1]
    out_y, out_l, out_r = [], [], []
    for yy in range(int(np.ceil(y.min())), int(np.floor(y.max())) + 1):
        s = y - yy
        i = np.flatnonzero((s[:-1] * s[1:] <= 0) & (s[:-1] != s[1:]))
        if i.size == 0:
            continue
        xc = x[i] + (x[i + 1] - x[i]) * s[i] / (s[i] - s[i + 1])
        out_y.append(yy)
        out_l.append(xc.min())
        out_r.append(xc.max())
    return (np.array(out_y), np.array(out_l, np.float32), np.array(out_r, np.float32))


# --------------------------------------------------------------------------- #
#  Core detection
# --------------------------------------------------------------------------- #
def polar_drop(M, Re, cut, zone_bottom, p, nth=360, band_win=0.5, fix_win=3.0,
               lam=0.03, max_step=1.5, min_meas=0.8):
    """
    Outline of a drop whose top lies inside the meniscus band, traced in polar
    coordinates around its centre by dynamic programming over the angle, with
    |dr| <= max_step px per 1-degree step.  Below the band r stays within
    +-fix_win px of the given mask M and follows the strongest outward edge
    (dark rim -> bright water).  Inside the band the drop acts as a lens and
    its top shows as a bright -> darker edge, so there either polarity counts
    (as for the water/oil interface in the band elsewhere).  Accepted only if
    the top arc shows a clear edge on >= min_meas of its points (a drop still
    attached to the surface by a neck has no edge across the neck).
    A flat top (sagitta < 6 % of the chord of the +-35 deg cap) is rejected:
    that is the band edge across the neck of a drop still hanging from the
    surface, not a cap.
    Returns (new mask, mean edge strength on the top arc) or None.
    """
    H, W = M.shape
    ys, xs = np.nonzero(M)
    if ys.size < 200:
        return None
    cy, cx = ys.mean(), xs.mean()
    th = np.roll(np.linspace(0, 2 * np.pi, nth, endpoint=False), -nth // 4)   # start at bottom
    dirs = np.stack([np.cos(th), np.sin(th)], 1)
    R0 = np.sqrt(ys.size / np.pi)
    step = 0.5
    rr = np.arange(0.2 * R0, 1.8 * R0, step)
    X = cx + dirs[:, :1] * rr[None, :]
    Y = cy + dirs[:, 1:] * rr[None, :]
    inside = map_coordinates((M > 0).astype(np.float32), [Y, X], order=0, mode="constant")
    last = np.where(inside.any(axis=1),
                    inside.shape[1] - 1 - np.argmax(inside[:, ::-1] > 0, axis=1), 0)
    r_m = rr[last]
    prof = map_coordinates(Re, [Y, X], order=1, mode="nearest")
    D = np.gradient(prof, step, axis=1)
    band = (cy + dirs[:, 1] * r_m) < zone_bottom
    # inside the band the drop acts as a lens: its top shows as a bright ->
    # darker edge (either polarity counts there); below: dark rim -> water
    E = np.where(band[:, None], np.minimum(np.abs(D), 0.08), np.minimum(D, 0.08))
    lo = np.where(band, np.maximum(r_m - band_win * R0, 0.2 * R0), r_m - fix_win)
    hi = np.where(band, r_m + band_win * R0, r_m + fix_win)
    E[(rr[None, :] < lo[:, None]) | (rr[None, :] > hi[:, None])] = -1.0
    E[Y < cut] = -1.0
    S = rr.size
    J = int(round(max_step / step))
    pen = lam * np.abs(np.arange(-J, J + 1)) * step
    j0 = int(np.argmin(np.abs(rr - r_m[0])))
    score = np.full(S, -np.inf)
    score[j0] = 0.0
    back = np.zeros((nth, S), np.int32)
    ar = np.arange(S)
    for i in range(nth):
        best = np.full(S, -np.inf)
        arg = np.zeros(S, np.int32)
        for kk, dj in enumerate(range(-J, J + 1)):
            src = ar - dj
            ok = (src >= 0) & (src < S)
            cand = np.full(S, -np.inf)
            cand[ok] = score[src[ok]] - pen[kk]
            better = cand > best
            best[better] = cand[better]
            arg[better] = src[better]
        score = best + E[i]
        back[i] = arg
    endp = score - lam * np.abs(ar - j0) * step
    j = np.zeros(nth, np.int32)
    j[-1] = int(np.argmax(endp))
    for i in range(nth - 1, 0, -1):
        j[i - 1] = back[i, j[i]]
    r = rr[j]
    top = band
    if top.sum() < 10:
        return None
    if (np.abs(D[np.arange(nth), j][top]) >= p.g_meas).mean() < min_meas:
        return None
    # a free drop has a rounded cap; a straight closing segment is the edge of
    # the band across the neck of a drop still hanging from the surface
    ang = np.degrees(np.arctan2(dirs[:, 1], dirs[:, 0]))
    cap = np.abs(ang + 90) <= 35
    cxp, cyp = cx + dirs[cap, 0] * r[cap], cy + dirs[cap, 1] * r[cap]
    o = np.argsort(cxp)
    cxp, cyp = cxp[o], cyp[o]
    chord = np.hypot(cxp[-1] - cxp[0], cyp[-1] - cyp[0])
    base = np.interp(cxp, [cxp[0], cxp[-1]], [cyp[0], cyp[-1]])
    if chord < 10 or (base - cyp).max() < 0.06 * chord:
        return None
    pts = np.stack([cx + dirs[:, 0] * r, cy + dirs[:, 1] * r], 1)
    m = np.zeros((H, W), np.uint8)
    cv2.fillPoly(m, [np.round(pts * 16).astype(np.int32).reshape(-1, 1, 2)], 255, cv2.LINE_8, shift=4)
    m[:cut] = 0
    return m, float(np.abs(D[np.arange(nth), j][top]).mean())


def drop_outline(outer, flags, Re, cut, zone_bottom, p, prev=None):
    """The drop left behind (no cavity).  Candidates: the outline traced up
    from below (`outer`), the same with its unmeasured top trimmed, and the
    previous frame's drop combined with it.  A candidate whose top in the band
    can be traced in polar coordinates (clear edge all along) is a detached
    drop; among those the one most like the previous frame wins (the top must
    not jump between the rounded cap and a lower stripe).  Otherwise the
    outline ends where the band hides the neck (flat top, not measured)."""
    H, W = Re.shape
    M_list, trimmed, t_flags = [], None, None
    if outer is not None and outer.any():
        trimmed, t_flags = trim_unmeasured_top(outer, flags, cut)
        M_list += [outer, trimmed]
    if prev is not None:
        M_list.append(prev if outer is None else (prev | (outer if trimmed is None else trimmed)))
    cands = []
    if p.drop_top:
        for M_ in M_list:
            if M_ is None or not M_.any():
                continue
            r_ = polar_drop(M_, Re, cut, zone_bottom, p)
            if r_ is not None:
                cands.append(r_)
    if cands:
        if prev is not None:
            pv = prev > 0
            def iou(m):
                m = m > 0
                return (m & pv).sum() / max((m | pv).sum(), 1)
            best = max(cands, key=lambda t: iou(t[0]))
            if iou(best[0]) < 0.6:
                cands = [] if outer is None else cands
                best = max(cands, key=lambda t: t[1]) if cands else None
        else:
            best = max(cands, key=lambda t: t[1])
        if best is not None:
            return best[0], np.zeros((2, H), bool)
    if trimmed is None:
        return np.zeros((H, W), np.uint8), np.zeros((2, H), bool)
    return trimmed, t_flags             # top cut where the band hides the neck


def trim_unmeasured_top(outer, flags, cut, run=8):
    """No cavity (the drop left behind): where the outline traced up through
    the meniscus band has no visible edge on a side for `run` rows in a row,
    the band hides the drop's neck -- instead of extrapolating it up to the
    surface, the outline ends there (the flat top is flagged as not measured).
    """
    xl, xr = row_edges(outer)
    ys = np.where(~np.isnan(xl))[0]
    if ys.size == 0 or ys[0] > cut + 1:
        return outer, flags
    y_cut = None
    for side in (0, 1):
        f = flags[side]
        for y in range(int(ys[-1]), int(ys[0]) - 1, -1):     # upward
            if f[y] and f[max(y - run + 1, 0):y + 1].all():
                yl = y + run - 1                                # lowest row of the run
                y_cut = yl if y_cut is None else max(y_cut, yl)
                break
    if y_cut is None:
        return outer, flags
    out = outer.copy()
    out[:y_cut + 1] = 0
    fl = flags.copy()
    fl[:, :y_cut + 1] = False
    fl[:, y_cut + 1:y_cut + 1 + run] = True     # the flat top (and its corners)
    return out, fl


class SequenceState:
    """What is carried from frame to frame in a video / stack:
      * satellites : small round bubbles at the surface, tracked so that they
                     stay excluded from the cavity in frames where the circle
                     detector misses them (held for `hold` frames)
      * air_alive  : the cavity collapses once; after it has been missing (or
                     less than `min_meas` measured) for `lost` consecutive
                     frames, no air is searched any more (the dark meniscus band
                     would otherwise be taken as air)
      * prev_air   : the previous cavity.  Inside the meniscus band the crater
                     bottom is only gray and striped; the previous cavity,
                     eroded by --prior-erode px, seeds 'surely air' there, so a
                     stripe cannot make the bottom jump up for a single frame,
                     and a new air region must overlap the previous one."""

    def __init__(self, hold=2, lost=2, min_meas=0.7):
        self.sats, self.hold, self.lost = [], hold, lost
        self.air_alive, self.had_air, self.missing = True, False, 0
        self.min_meas, self.weak = min_meas, 0
        self.prev_air = None          # final air mask of the previous frame
        self.prev_drop = None         # last outer mask of the drop left behind
        self.bottoms = []             # cavity bottom y of the previous frames
        self.rise = 0.0               # how fast it rose in the last frame (px)

    def satellites(self, det, redetect=None):
        """det: circles found in this frame; redetect(list) -> circles found
        near the given previous positions with a lower threshold.  A bubble
        missed by both is kept at its last position for `hold` frames."""
        tracks = [[x, y, r, 0] for x, y, r in det]
        missed = [t for t in self.sats
                  if all(np.hypot(t[0] - d[0], t[1] - d[1]) > max(10, t[2]) for d in tracks)]
        for t in missed:
            found = redetect([(t[0], t[1], t[2])]) if redetect is not None else []
            if found:
                x, y, r = found[0]
                if all(np.hypot(x - d[0], y - d[1]) > max(10, r) for d in tracks):
                    tracks.append([x, y, r, 0])
            elif t[3] + 1 <= self.hold:
                tracks.append([t[0], t[1], t[2], t[3] + 1])
        self.sats = tracks
        return [(x, y, r) for x, y, r, _ in tracks]

    def update(self, res):
        if res.get("air_end"):                   # relaxed: tracking ends for good
            self.air_alive = False
        if res["outer_curve"] is not None and res["inner_curve"] is None and self.had_air:
            self.prev_drop = res["outer"]
        elif res["inner_curve"] is not None:
            self.prev_drop = None
        if res["inner_curve"] is not None:       # else: keep the last good cavity
            self.prev_air = res["inner"]
            self.bottoms.append(float(res["inner_curve"][:, 1].max()))
            b = self.bottoms
            # sustained rise over the last two frames (a single jump is noise)
            self.rise = (max(0.0, min(b[-3] - b[-2], b[-2] - b[-1])) if len(b) > 2 else 0.0)
            # a tracked crater that is mostly extrapolated for `lost` frames in a
            # row is no longer visible as such: stop tracking it
            mf = res.get("inner_meas_frac")
            if self.had_air and mf is not None and mf < self.min_meas:
                self.weak += 1
                if self.weak >= self.lost:
                    self.air_alive = False
            else:
                self.weak = 0
        if res["inner_curve"] is not None:
            self.had_air, self.missing = True, 0
        elif self.had_air:
            self.missing += 1
            if self.missing >= self.lost:
                self.air_alive = False


def detect_frame(frame, bg, surface_y, zone_bottom, p, seed=None, state=None):
    """Return a dict with ratio image, masks, sub-pixel curves and flags.
    `state` (SequenceState) carries satellites / cavity lifetime in a sequence."""
    R, Re, gx, gy = compute_images(frame, bg, p)
    H, W = R.shape
    cut = min(max(surface_y + p.surface_margin, 0), H - 5)
    zone_bottom = max(zone_bottom, cut + 1)

    # ---------- reliable lower object (below the free-surface zone)
    thr = (R < 1.0 - p.t_out).astype(np.uint8) * 255
    thr[:cut] = 0
    thr = cv2.morphologyEx(thr, cv2.MORPH_OPEN, disk(p.open_r))
    thr = cv2.morphologyEx(thr, cv2.MORPH_CLOSE, disk(p.close_r))
    lower = thr.copy()
    lower[:zone_bottom] = 0
    lower = pick_component(lower, seed, p.min_area, True)
    obj = lower if lower.any() else pick_component(thr, seed, p.min_area, True)
    c = np.where(obj.any(axis=0))[0]
    obj_x = (c[0] - 20, c[-1] + 20) if c.size else None

    # ---------- air cavity (inner, oil/air)
    sats = find_satellites(R, cut, zone_bottom, lower=lower, t_air=p.t_air) if p.satellites else []
    if state is not None and p.satellites:
        sats = state.satellites(sats, lambda near: find_satellites(
            R, cut, zone_bottom, param2=12, lower=lower, near=near, t_air=p.t_air))
    prior = state.prev_air if state is not None else None
    if state is None or state.air_alive:
        # the prior is eroded more while the crater bottom is still rising fast
        er = p.prior_erode + (1.5 * state.rise if state is not None else 0)
        air = segment_air(R, gx, gy, cut, zone_bottom, obj_x, p, sats, prior,
                          int(min(er, 40)))
    else:
        air = np.zeros((H, W), np.uint8)
    air_flags = np.zeros((2, H), bool)
    sink_lim = None
    air_end = False                      # the tracked crater has relaxed: stop
    air_reason = ""
    if air.any() and prior is not None and p.max_sink >= 0:
        # inside the band the crater only rises / widens while it collapses and
        # relaxes: it may grow sideways and upward, but by at most max_sink px
        # per frame downward (keeps it out of the gray oil neck above the drop)
        # previous bottom profile, narrow pockets removed, spread +-15 px sideways
        from scipy.ndimage import grey_opening, maximum_filter1d
        pm = prior > 0
        has = pm.any(axis=0)
        ybp = np.where(has, H - 1 - np.argmax(pm[::-1], axis=0), -10 ** 6).astype(float)
        c_ = np.flatnonzero(has)
        ybp[c_] = grey_opening(ybp[c_], size=p.bottom_width, mode="nearest")
        ybl = maximum_filter1d(ybp, size=31, mode="nearest")
        # only the crater BOTTOM is limited (columns where the previous crater
        # was deeper than 60 % of its depth); the walls may move out and down
        # freely as the crater widens
        dep = ybp[c_].max() - cut if c_.size else 0
        bottom = has & (ybp > cut + 0.6 * dep)
        ybl = np.where(bottom, ybl, np.inf)
        allowed = np.arange(H)[:, None] <= (ybl + p.max_sink)[None, :]
        sink_lim = ybl + p.max_sink
        band = air[:zone_bottom] > 0
        air[:zone_bottom] = np.where(band & allowed[:zone_bottom], 255, 0).astype(np.uint8)
        n_, l_, s_, _ = cv2.connectedComponentsWithStats(air, 8)
        if n_ > 2:
            air = np.where(l_ == 1 + int(np.argmax(s_[1:, cv2.CC_STAT_AREA])), 255, 0).astype(np.uint8)
        # (no row fill here: it would bring back what the limit removed)
    if air.any():
        cols = np.where(air.any(axis=0))[0]
        rows_ = np.where(air.any(axis=1))[0]
        m_ = max(5, int(W * p.margin_frac))
        # a cavity that is being tracked may get shallow; a new one must be deep
        dmin = p.min_depth_track if prior is not None else p.min_depth_air
        if (rows_[-1] - cut < dmin or
                (air > 0).sum() / max(np.ptp(cols) + 1, 1) < 0.4 * dmin):
            air[:] = 0                   # only a dark streak under the surface: no cavity
            air_reason = "too shallow"
        elif p.row_norm and (cols[0] < m_ or cols[-1] >= W - m_):
            air[:] = 0                   # crater spread into the reference margins:
            air_end = prior is not None  # it has relaxed into the free surface (and
            air_reason = "reaches the image margins"
            #                              the row normalisation is no longer valid)
        elif prior is not None and crater_relief(air) < p.min_relief:
            air[:] = 0                   # flat: the crater has relaxed into the surface
            air_end = True
            air_reason = "flat (relaxed)"
        elif ((R < p.t_air) & (air > 0)).sum() < p.min_core_frac * (air > 0).sum():
            air[:] = 0                   # no black left in it: the crater has relaxed
            air_end = prior is not None
            air_reason = "no black left"
        elif prior is not None and (((air > 0) & (prior > 0)).sum() < 0.5 * (air > 0).sum() or
                                    (air > 0).sum() < 0.6 * (prior > 0).sum()):
            air[:] = 0                   # not (or only a piece of) the previous cavity
            air_reason = "inconsistent with previous frame"
    if air.any():
        air, air_flags = extend_air(air, R, gx, gy, cut, p)
        air, sn = snap_to_surface(air, cut)
        if sn is not None:
            air_flags[:, sn[0]:sn[1]] = True
        air = trim_top_flare(air, cut)
        air, air_flags = retrace_top(air, air_flags, R, gx, gy, cut, zone_bottom, p, sats)
        air, air_flags = retrace_rim_shallow(air, air_flags, R, gx, gy, cut, zone_bottom, p)

    # ---------- whole object (outer, water/oil)
    if lower.any():
        outer, out_flags = track_outer(lower, air, air_flags, R, gx, cut, p)
        if not air.any():
            outer, out_flags = drop_outline(outer, out_flags, Re, cut, zone_bottom, p,
                                            state.prev_drop if state is not None else None)
    elif (not air.any() and state is not None and state.prev_drop is not None
          and p.drop_top):
        # nothing below the band: the drop has risen into it -- follow it
        # from the previous frame if its outline is visible all around
        outer, out_flags = drop_outline(None, None, Re, cut, zone_bottom, p, state.prev_drop)
    elif air.any():
        outer, out_flags = obj.copy(), np.zeros((2, H), bool)
    else:
        # nothing below the meniscus band and no cavity: the object (if any)
        # is inside the band, where it cannot be separated reliably
        outer, out_flags = np.zeros((H, W), np.uint8), np.zeros((2, H), bool)
    outer = fill_rows(outer | air) if outer.any() or air.any() else outer
    outer = remove_notches(outer, cut, True, p.notch)
    outer, sn = snap_to_surface(outer, cut)
    if sn is not None:
        out_flags[:, sn[0]:sn[1]] = True

    # ---------- sub-pixel interfaces
    ic, ist, icl, iraw = (refine_interface(air, Re, cut, p.win_in_air, p.win_out_air, p.lam,
                                           dip_tol=p.dip_tol)
                          if air.any() else (None, None, False, None))
    oc, ost, ocl, oraw = (refine_interface(outer, Re, cut, p.win_in_out, p.win_out_out, p.lam,
                                           rise_tol=p.rise_tol,
                                           abs_above=zone_bottom)
                          if outer.any() else (None, None, False, None))
    if ic is not None and sink_lim is not None:
        # the refined cavity bottom may not sink below the limit either
        xi = np.clip(np.round(ic[:, 0]).astype(int), 0, W - 1)
        lim = sink_lim[xi] + 1.0
        inb = ic[:, 1] < zone_bottom
        ic[:, 1] = np.where(inb & (ic[:, 1] > lim), lim, ic[:, 1])
    # smooth profiles; strength re-measured on the smoothed curves
    imeas = omeas = None
    ocontact = None
    meas_frac_track = None
    if ic is not None:
        ic = remove_folds(remove_loops(smooth_curve(remove_folds(remove_loops(ic)), icl, p.smooth)))
        if p.smooth_band > 0:
            ic = smooth_band_shallow(ic, icl, zone_bottom, cut, p.smooth_band)
        ist = curve_strength(ic, icl, Re, air)
        imeas = ~row_flags_to_points(ic, air_flags) & (ist >= p.g_meas)
        meas_frac_track = float(imeas.mean())
        if not icl:
            ic, imeas = smooth_ends(ic, imeas, cut, zone_bottom)
            ic2 = remove_loops(ic)
            if len(ic2) != len(ic):
                imeas = _resample_flags(ic, imeas, ic2)
                ic = ic2
            ist = curve_strength(ic, icl, Re, air)
    if oc is not None:
        oc = remove_folds(remove_loops(smooth_curve(remove_folds(remove_loops(oc)), ocl, p.smooth)))
        if p.smooth_band > 0:
            oc = smooth_band_shallow(oc, ocl, zone_bottom, cut, p.smooth_band)
        ost = curve_strength(oc, ocl, Re, outer, absolute_above=zone_bottom)
        omeas = ~row_flags_to_points(oc, out_flags) & (ost >= p.g_meas)
        if not ocl:
            oc, omeas = smooth_ends(oc, omeas, cut, zone_bottom)
            oc2 = remove_loops(oc)
            if len(oc2) != len(oc):
                omeas = _resample_flags(oc, omeas, oc2)
                oc = oc2
            ost = curve_strength(oc, ocl, Re, outer, absolute_above=zone_bottom)
        ocontact = np.zeros(len(oc), bool)
        if ic is not None and not ocl and not icl:
            oc, omeas, ocontact = merge_contact(oc, omeas, ic, imeas, p.contact_d)
            ost = curve_strength(oc, ocl, Re, outer, absolute_above=zone_bottom)
            ost[ocontact] = curve_strength(oc, ocl, Re, outer)[ocontact]
    inner_m = curve_to_mask(ic, (H, W))
    outer_m = curve_to_mask(oc, (H, W)) | inner_m
    res = dict(ratio=R, outer=outer_m, inner=inner_m, cut=cut,
               outer_curve=oc, inner_curve=ic, outer_closed=ocl, inner_closed=icl,
               outer_c=oraw, inner_c=iraw, outer_meas=omeas, inner_meas=imeas,
               outer_strength=ost, inner_strength=ist, outer_contact=ocontact,
               outer_seg=outer, inner_seg=air, air_end=air_end, air_reason=air_reason,
               inner_meas_frac=meas_frac_track,
               outer_top_cut=bool(oc is not None and ic is None and ocl and
                                  out_flags.any()))
    if state is not None:
        state.update(res)
    return res


# --------------------------------------------------------------------------- #
#  Metrics
# --------------------------------------------------------------------------- #
def metrics(res, px_per_mm=None):
    """Simple geometric quantities from the (curve-derived) masks, in px or mm."""
    s = 1.0 / px_per_mm if px_per_mm else 1.0
    out = {}
    for name in ("outer", "inner"):
        m = res[name] > 0
        a = m.sum()
        out[f"{name}_area"] = a * s * s if res[f"{name}_curve"] is not None else np.nan
        out[f"{name}_eq_radius"] = np.sqrt(a / np.pi) * s if a else np.nan
        c = res[f"{name}_curve"]
        if a and c is not None:
            ys, xs = np.nonzero(m)
            out[f"{name}_cx"] = xs.mean() * s
            out[f"{name}_cy"] = ys.mean() * s
            out[f"{name}_bottom_y"] = float(c[:, 1].max()) * s          # sub-pixel
            out[f"{name}_width"] = float(np.ptp(c[:, 0])) * s
        else:
            for k in ("cx", "cy", "bottom_y", "width"):
                out[f"{name}_{k}"] = np.nan
    # oil-film thickness at the bottom, along the vertical through the air centroid
    out["oil_thickness_bottom"] = np.nan
    ic, oc = res["inner_curve"], res["outer_curve"]
    if ic is not None and oc is not None and not np.isnan(out["inner_cx"]):
        x0 = out["inner_cx"] / s

        def lowest_crossing(c):
            x, y = c[:, 0], c[:, 1]
            d = x - x0
            i = np.flatnonzero((d[:-1] * d[1:] <= 0) & (d[:-1] != d[1:]))
            if i.size == 0:
                return np.nan
            return float((y[i] + (y[i + 1] - y[i]) * d[i] / (d[i] - d[i + 1])).max())
        out["oil_thickness_bottom"] = (lowest_crossing(oc) - lowest_crossing(ic)) * s
    out["oil_area"] = out["outer_area"] - np.nan_to_num(out["inner_area"])
    return out


# --------------------------------------------------------------------------- #
#  Drawing
# --------------------------------------------------------------------------- #
def measured_points(res, key):
    """Boolean per curve point: True = measured, False = extrapolated through a
    hidden region near the free surface / no clear edge."""
    m = res.get(f"{key}_meas")
    c = res[f"{key}_curve"]
    if m is None:
        return np.ones(len(c), bool)
    return _clean_flags(m)


def _clean_flags(m, min_run=4):
    """Flip unmeasured runs shorter than `min_run` points to measured (single
    weak points on a clear edge), keep longer ones."""
    m = m.copy()
    n = m.size
    i = 0
    while i < n:
        if not m[i]:
            j = i
            while j < n and not m[j]:
                j += 1
            if j - i < min_run and i > 0 and j < n:
                m[i:j] = True
            i = j
        else:
            i += 1
    return m


def _draw_curve(vis, q, obs, col, thickness, closed=False, mask=None, dash=0):
    """Draw an ordered curve (16x fixed-point points).  Thick = measured,
    thin & lighter = not measured.  `mask`: draw only these points' segments.
    `dash` > 0: draw only every other `dash`-px stretch (dashed line)."""
    light = tuple(int(0.45 * v + 0.55 * 255) for v in col)
    n = len(q)
    if n < 2:
        return
    arc = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(q / 16.0, axis=0), axis=1))])
    for j in range(n if closed else n - 1):
        j2 = (j + 1) % n
        if mask is not None and not (mask[j] and mask[j2]):
            continue
        if dash and int(arc[j] // dash) % 2 == 1:
            continue
        m = obs[j] and obs[j2]
        cv2.line(vis, tuple(q[j]), tuple(q[j2]), col if m else light,
                 thickness if m else 1, cv2.LINE_AA, shift=4)


def draw(frame, res, label=None, thickness=2, show_surface=True, legend=True):
    """Annotated frame: water/oil (cyan), oil/air (magenta); where both are
    the same water/air curve (no oil) it is drawn magenta with cyan dashes."""
    vis = cv2.cvtColor(np.clip(frame, 0, 255).astype(np.uint8), cv2.COLOR_GRAY2BGR)
    if show_surface:
        cv2.line(vis, (0, res["cut"]), (vis.shape[1] - 1, res["cut"]),
                 SURF_COLOR, 1, cv2.LINE_AA)
    oc, ic = res["outer_curve"], res["inner_curve"]
    contact = res.get("outer_contact")
    if oc is not None and len(oc) > 1:
        q = np.round(oc * 16).astype(np.int32)
        own = None if contact is None or not contact.any() else ~contact
        if own is not None:                     # the joins at the triple points
            own = own | np.r_[own[1:], False] | np.r_[False, own[:-1]]
        _draw_curve(vis, q, measured_points(res, "outer"), OUTER_COLOR, thickness,
                    bool(res["outer_closed"]), own)
    if ic is not None and len(ic) > 1:
        q = np.round(ic * 16).astype(np.int32)
        _draw_curve(vis, q, measured_points(res, "inner"), INNER_COLOR, thickness,
                    bool(res["inner_closed"]))
    if oc is not None and contact is not None and contact.any():
        q = np.round(oc * 16).astype(np.int32)
        _draw_curve(vis, q, measured_points(res, "outer"), OUTER_COLOR, thickness,
                    False, contact, dash=7)
    if legend:
        x0, y = vis.shape[1] - 190, 22
        for txt, cols in (("water/oil", [OUTER_COLOR]), ("oil/air", [INNER_COLOR]),
                          ("water/air (both)", [INNER_COLOR, OUTER_COLOR])):
            for k in range(4):
                cv2.line(vis, (x0 + 7 * k, y - 5), (x0 + 7 * k + 6, y - 5),
                         cols[k % len(cols)], 2, cv2.LINE_AA)
            cv2.putText(vis, txt, (x0 + 34, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                        cols[-1] if len(cols) == 1 else (255, 255, 255), 2 if len(cols) == 1 else 1,
                        cv2.LINE_AA)
            y += 22
    if label:
        cv2.putText(vis, label, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                    (0, 0, 255), 2, cv2.LINE_AA)
    return vis


def debug_panel(frame, res):
    r = np.clip(res["ratio"] / 1.3 * 255, 0, 255).astype(np.uint8)
    r = cv2.cvtColor(r, cv2.COLOR_GRAY2BGR)
    m = np.zeros_like(r)
    m[res["outer"] > 0] = (120, 120, 0)
    m[res["inner"] > 0] = (200, 0, 200)
    top = np.hstack([draw(frame, res), draw(res["ratio"] / 1.3 * 255, res, show_surface=False)])
    bot = np.hstack([m, cv2.addWeighted(r, 0.6, m, 0.8, 0)])
    for img, t in ((top[:, r.shape[1]:], "ratio = frame/background"),
                   (bot[:, :r.shape[1]], "masks"),
                   (bot[:, r.shape[1]:], "overlay")):
        cv2.putText(img, t, (10, img.shape[0] - 12), cv2.FONT_HERSHEY_SIMPLEX,
                    0.6, (0, 255, 0), 2, cv2.LINE_AA)
    return np.vstack([top, bot])


def plot_profiles(profiles, surface_y, fn, fps, frame0):
    """Overlay of the interface curves of all frames with an air cavity,
    coloured by time (capillary-wave view); bold = measured, thin = extrapolated."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return False
    if not profiles:
        return False
    # the collapse (frames with an air cavity) is what the plot is for; the
    # drop left behind afterwards would bury it
    with_air = {f for f, _, _ in profiles.get("inner", [])}
    if with_air:
        profiles = {k: [t for t in v if t[0] in with_air] for k, v in profiles.items()}
    fig, axes = plt.subplots(1, 2, figsize=(14, 6), sharex=True, sharey=True)
    frames = sorted({f for v in profiles.values() for f, _, _ in v})
    cmap = plt.get_cmap("viridis")
    norm = matplotlib.colors.Normalize(frames[0] / fps * 1e3, max(frames[-1], frames[0] + 1) / fps * 1e3)
    for ax, key, title in ((axes[0], "inner", "oil / air interface"),
                           (axes[1], "outer", "water / oil interface")):
        ax.imshow(frame0, cmap="gray", alpha=0.35)
        for f, c, m in profiles.get(key, []):
            col = cmap(norm(f / fps * 1e3))
            ax.plot(c[:, 0], c[:, 1], color=col, lw=0.4, alpha=0.5)
            cm = np.where(m[:, None], c, np.nan)                  # measured part bold
            ax.plot(cm[:, 0], cm[:, 1], color=col, lw=0.9)
        ax.axhline(surface_y, color="orange", lw=0.8, ls="--")
        ax.set_title(title)
        ax.set_xlabel("x [px]")
    axes[0].set_ylabel("y [px]")
    sm = plt.cm.ScalarMappable(norm=norm, cmap=cmap)
    fig.colorbar(sm, ax=axes, label="t [ms]", shrink=0.8)
    fig.savefig(fn, dpi=130, bbox_inches="tight")
    plt.close(fig)
    return True


# --------------------------------------------------------------------------- #
#  Main
# --------------------------------------------------------------------------- #
def build_parser():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", help="video, TIFF stack or image")
    ap.add_argument("--out", default="interfaces_out", help="output directory")
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--stop", type=int, default=None)
    ap.add_argument("--step", type=int, default=1)
    ap.add_argument("--fps", type=float, default=10000.0, help="recording frame rate")
    ap.add_argument("--px-per-mm", type=float, default=None,
                    help="spatial calibration; metrics in mm if given, else px")
    # background
    ap.add_argument("--bg", default=None, help="background image file (no bubble)")
    ap.add_argument("--bg-mode", choices=["last", "first", "margins"], default="last",
                    help="background from last/first N frames, or image margins")
    ap.add_argument("--bg-n", type=int, default=15, help="N frames for background")
    ap.add_argument("--no-bg-clean", dest="bg_clean", action="store_false",
                    help="do not patch objects left in the background frames")
    ap.add_argument("--no-row-norm", dest="row_norm", action="store_false",
                    help="disable row-wise normalisation by the image margins")
    ap.add_argument("--margin-frac", type=float, default=0.10,
                    help="width fraction of each side margin used as reference")
    # geometry
    ap.add_argument("--surface-y", type=int, default=None,
                    help="row of the free surface (auto-detected if omitted)")
    ap.add_argument("--surface-margin", type=int, default=6,
                    help="ignore this many rows below the free surface")
    ap.add_argument("--surface-zone", type=int, default=None,
                    help="height (px) of the meniscus band below the surface (auto if omitted)")
    ap.add_argument("--seed", type=float, nargs=2, default=None, metavar=("X", "Y"),
                    help="a pixel inside the bubble (default: image centre)")
    # segmentation
    ap.add_argument("--t-out", type=float, default=0.15,
                    help="ratio below (1-t_out) x local water = not water (outer interface)")
    ap.add_argument("--t-lens", type=float, default=0.20,
                    help="in the band, oil brighter than (1+t_lens) x local water is oil too")
    ap.add_argument("--t-air", type=float, default=0.25,
                    help="ratio below this = surely air (watershed marker)")
    ap.add_argument("--t-bright", type=float, default=0.55,
                    help="ratio above this = surely not air (watershed marker)")
    ap.add_argument("--t-air-hi", type=float, default=0.55,
                    help="a traced cavity wall needs ratio < this just inside it")
    ap.add_argument("--air-reach", type=int, default=6,
                    help="below the band the cavity edge lies within this many px of "
                         "'surely air' (ratio < t_air) pixels; 0 = off")
    ap.add_argument("--bay", type=int, default=41,
                    help="max height (rows) of bays in the cavity wall inside the band "
                         "that are closed (wall hidden by a light stripe); 0 = off")
    ap.add_argument("--no-satellites", dest="satellites", action="store_false",
                    help="do not look for small round bubbles/drops at the surface "
                         "(excluded from the cavity)")
    ap.add_argument("--min-depth-air", type=float, default=30,
                    help="an air region reaching less deep than this (px below the free "
                         "surface cut) is surface shadow, not a cavity")
    ap.add_argument("--min-depth-track", type=float, default=15,
                    help="same for a cavity already tracked in the previous frames "
                         "(tracking ends when the crater is shallower)")
    ap.add_argument("--min-core-frac", type=float, default=0.05,
                    help="an air region needs at least this fraction of 'surely air' "
                         "(ratio < t_air) pixels; tracking ends when the crater has none")
    ap.add_argument("--max-sink", type=int, default=2,
                    help="px per frame the crater may extend downward inside the band "
                         "(video/stack only; -1 = off)")
    ap.add_argument("--t-prior", type=float, default=0.45,
                    help="the previous cavity seeds air only where ratio < this")
    ap.add_argument("--min-relief", type=float, default=12,
                    help="a tracked crater must be at least this many px deeper in its "
                         "middle than at its rim; tracking ends when it has relaxed flat")
    ap.add_argument("--prior-erode", type=int, default=12,
                    help="inside the band, the previous cavity eroded by this many px "
                         "seeds 'surely air' (video/stack only; 0 = off)")
    ap.add_argument("--bottom-width", type=int, default=81,
                    help="narrow pockets / notches in the crater bottom inside the band "
                         "(narrower than this, px) are removed")
    ap.add_argument("--no-drop-top", dest="drop_top", action="store_false",
                    help="do not trace the top of a detached drop inside the band")
    ap.add_argument("--dip-tol-wall", type=float, default=0.1,
                    help="re-traced walls stop at the first bright ridge (drop > this "
                         "after a rise) met going outward from the crater")
    ap.add_argument("--shallow-slope", type=float, default=1.0,
                    help="crater walls flatter than this (dy/dx) where they enter the top "
                         "rows get a smooth parametric rim instead of a row-wise trace")
    ap.add_argument("--rim-keep", type=float, default=0.6,
                    help="the smooth parametric rim replaces the segmented one if it has at "
                         "least this fraction of its edge evidence")
    ap.add_argument("--top-rows", type=int, default=45,
                    help="the walls in this many rows below the surface are re-traced as "
                         "smooth continuations of the wall below (dark stripe of the band)")
    ap.add_argument("--notch", type=int, default=9,
                    help="horizontal slits/notches up to this many rows tall are closed")
    ap.add_argument("--no-row-fill", dest="row_fill", action="store_false",
                    help=argparse.SUPPRESS)
    ap.add_argument("--blur", type=float, default=1.5, help="Gaussian sigma for segmentation (px)")
    ap.add_argument("--edge-sigma", type=float, default=1.0,
                    help="Gaussian sigma for sub-pixel edge localisation (px)")
    ap.add_argument("--open-r", type=int, default=2)
    ap.add_argument("--close-r", type=int, default=4)
    ap.add_argument("--open-r-air", type=int, default=1)
    ap.add_argument("--min-area", type=int, default=300)
    ap.add_argument("--min-area-air", type=int, default=150)
    # sub-pixel refinement
    ap.add_argument("--win-in-air", type=float, default=4.0,
                    help="px the oil/air edge may move into the air during refinement")
    ap.add_argument("--win-out-air", type=float, default=16.0,
                    help="px the oil/air edge may move outward (only across a gray zone)")
    ap.add_argument("--dip-tol", type=float, default=0.05,
                    help="max darkening (ratio) allowed on the way outward")
    ap.add_argument("--win-in-out", type=float, default=8.0,
                    help="px the water/oil edge may move inward (only down a darkening ramp)")
    ap.add_argument("--rise-tol", type=float, default=0.05,
                    help="max brightening (ratio) allowed on the way inward (water/oil edge)")
    ap.add_argument("--win-out-out", type=float, default=3.0)
    ap.add_argument("--lam", type=float, default=0.06,
                    help="smoothness of the refined interface (penalty per px offset change)")
    ap.add_argument("--smooth", type=float, default=4.0,
                    help="Gaussian smoothing of the final profiles along their arc length "
                         "(px); 0 = off")
    ap.add_argument("--smooth-band", type=float, default=10.0,
                    help="stronger smoothing (px) of flat stretches inside the meniscus band "
                         "(late shallow crater: stripe staircase); 0 = off")
    ap.add_argument("--contact-d", type=float, default=3.0,
                    help="where the water/oil interface is closer than this (px) to the "
                         "oil/air one there is no oil: both are the same water/air curve")
    ap.add_argument("--g-meas", type=float, default=0.03,
                    help="min edge strength (d ratio/d n, 1/px) for a point to count as measured")
    # output
    ap.add_argument("--debug", type=int, nargs="*", default=None,
                    help="write debug panels for these frame indices and exit")
    ap.add_argument("--save-frames", action="store_true",
                    help="also write every annotated frame as PNG")
    ap.add_argument("--video-fps", type=float, default=30.0,
                    help="playback fps of the annotated video")
    return ap


def default_params(**kw):
    p = build_parser().parse_args(["dummy"])
    for k, v in kw.items():
        setattr(p, k, v)
    return p


def main():
    p = build_parser().parse_args()
    os.makedirs(p.out, exist_ok=True)
    name = os.path.splitext(os.path.basename(p.input))[0]

    print(f"Loading {p.input} ...")
    all_frames, _ = load_frames(p.input)          # full sequence for the background
    print(f"  {len(all_frames)} frames, {all_frames[0].shape[1]}x{all_frames[0].shape[0]}")

    if p.bg:
        bg = to_gray(cv2.imread(p.bg, cv2.IMREAD_UNCHANGED))
    else:
        bg = estimate_background(all_frames, p.bg_mode, p.bg_n, p.bg_clean)
    ref = bg if bg is not None else background_from_margins(all_frames[0])

    surface_y = p.surface_y if p.surface_y is not None else detect_surface_y(ref)
    print(f"  free surface at y = {surface_y} px{' (auto)' if p.surface_y is None else ''}")
    zone_bottom = (surface_y + p.surface_zone if p.surface_zone is not None
                   else detect_zone_bottom(ref, surface_y))
    print(f"  free-surface zone: y = {surface_y} .. {zone_bottom} px")

    stop = len(all_frames) if p.stop is None else min(p.stop, len(all_frames))
    sel = list(range(p.start, stop, p.step))

    if p.debug is not None:
        for i in (p.debug or [sel[0]]):
            res = detect_frame(all_frames[i], bg, surface_y, zone_bottom, p, p.seed)
            fn = os.path.join(p.out, f"{name}_debug_{i:04d}.png")
            cv2.imwrite(fn, debug_panel(all_frames[i], res))
            print("  wrote", fn)
        return

    h, w = all_frames[0].shape
    vid_fn = os.path.join(p.out, f"{name}_annotated.mp4")
    writer = cv2.VideoWriter(vid_fn, cv2.VideoWriter_fourcc(*"mp4v"), p.video_fps, (w, h))
    rows, contours, curves = [], {}, {}
    unit = "mm" if p.px_per_mm else "px"

    state = SequenceState()
    for n, i in enumerate(sel):
        frame = all_frames[i]
        res = detect_frame(frame, bg, surface_y, zone_bottom, p, p.seed, state)
        t_ms = i / p.fps * 1e3
        vis = draw(frame, res, f"frame {i}   t = {t_ms:.2f} ms")
        writer.write(vis)
        if p.save_frames:
            cv2.imwrite(os.path.join(p.out, f"{name}_{i:05d}.png"), vis)

        m = metrics(res, p.px_per_mm)
        for key in ("inner", "outer"):
            c = res[f"{key}_curve"]
            m[f"{key}_measured_frac"] = float(measured_points(res, key).mean()) if c is not None else np.nan
        # 1 = drop outline cut flat where the band hides its neck (still hanging
        #     from the surface): its area / centroid describe only the visible part
        m["outer_top_cut"] = int(res.get("outer_top_cut", False))
        oc_c = res.get("outer_contact")
        m["water_air_contact_frac"] = (float(oc_c.mean()) if oc_c is not None and
                                       res["inner_curve"] is not None else np.nan)
        # 1 = no cavity and the drop outline closes inside the meniscus band:
        #     the drop may still hang from the surface by a neck hidden there
        oc_ = res["outer_curve"]
        m["outer_top_in_band"] = int(res["inner_curve"] is None and oc_ is not None
                                     and float(oc_[:, 1].min()) < zone_bottom)
        m.update(frame=i, time_ms=t_ms)
        rows.append(m)
        for key in ("outer", "inner"):
            c = res[f"{key}_curve"]
            if c is None:
                continue
            ok = measured_points(res, key)
            contours[f"{key}_curve_{i:05d}"] = c.astype(np.float32)
            contours[f"{key}_measured_{i:05d}"] = ok
            contours[f"{key}_strength_{i:05d}"] = res[f"{key}_strength"].astype(np.float32)
            if key == "outer" and res.get("outer_contact") is not None:
                contours[f"outer_contact_{i:05d}"] = res["outer_contact"]
            if res[f"{key}_c"] is not None:
                contours[f"{key}_{i:05d}"] = res[f"{key}_c"][:, 0, :]
            yy, xl, xr = curve_row_profile(c)
            contours[f"{key}_prof_{i:05d}"] = np.stack([yy, xl, xr], 1)
            curves.setdefault(key, []).append((i, c, ok))
        if n % 50 == 0:
            print(f"  frame {i}: outer area {m['outer_area']:.0f}, "
                  f"inner area {m['inner_area']:.0f} {unit}^2")
    writer.release()

    csv_fn = os.path.join(p.out, f"{name}_metrics.csv")
    keys = ["frame", "time_ms"] + [k for k in rows[0] if k not in ("frame", "time_ms")]
    with open(csv_fn, "w", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=keys)
        wr.writeheader()
        for r in rows:
            wr.writerow({k: (f"{r[k]:.4f}" if isinstance(r[k], float) else r[k]) for k in keys})

    npz_fn = os.path.join(p.out, f"{name}_contours.npz")
    np.savez_compressed(npz_fn, surface_y=surface_y, cut_y=surface_y + p.surface_margin,
                        zone_bottom=zone_bottom, **contours)

    plot_fn = os.path.join(p.out, f"{name}_profiles.png")
    if plot_profiles(curves, surface_y, plot_fn, p.fps, all_frames[sel[0]]):
        print(f"  {plot_fn}")
    print(f"Done.\n  {vid_fn}\n  {csv_fn}\n  {npz_fn}  (contours: pixels)")


if __name__ == "__main__":
    main()