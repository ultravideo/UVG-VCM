#!/usr/bin/env python3
"""Convert testbench annotations (<name>_annotations.json, + <name>_masks/) into a CVAT 1.1 video XML for import.

The reverse of cvat_to_json.py.

Output: one "CVAT for video 1.1" XML with a minimal <meta><task> section (size, labels, one segment, original_size).
- Box tracks: one per JSON track_id (in track_id order), CVAT track ids 0, 1, 2, ...
- Polygon tracks: one per object that has a polygon, ids continuing after the box tracks, in the same order.
  The polygon is the JSON "polygon" (normalised); if an object has none but has a "mask_color" and the masks folder
  exists, it is traced from its mask: the outer outline of each connected region (cv2.findContours, external),
  simplified with --epsilon pixels (approxPolyDP; 0 = every boundary pixel). A CVAT track has one polygon per
  frame, so several regions (an object split by an occluder) are joined into one polygon by zero-width bridges
  (--regions all, default; drawn, the bridge is a 1-pixel line) or only the largest is kept (--regions largest).
  Holes are filled. An object with no mask pixels in a frame has no polygon there.
- Pairing: each box track and its polygon track share a CVAT group (group_id = box track id + 1), which
  cvat_to_json.py uses to pair them (otherwise it pairs by IoU); a box track without polygons is alone in its group.
- Frames: JSON key "1" -> CVAT frame 0. Size = the largest frame key. Every shape is a keyframe; where a track is
  absent (gap, or after its last frame) an outside="1" copy of the previous shape ends it, so CVAT does not
  interpolate across the gap.
- Coordinates: normalised [0, 1] -> pixels at the original size (--size WxH, default: the size of the mask PNGs).
- Labels: the COCO name of class_id (labels.py); cvat_to_json.py maps them back.
- iscrowd = 1 objects: the shapes get the label attribute "iscrowd" (checkbox) = true; read back by cvat_to_json.py.
  The CVAT task must have this attribute on the label, else use --no-crowd-attribute (exported as normal objects).
- A track_id that occurs twice in one frame: the second object goes to an extra track (reported).
Not in the XML: track ids (re-numbered 1, 2, ... in box-track order by cvat_to_json.py) and mask colours.

Usage
  json_to_cvat.py WinterDrive_annotations.json \\
      --out WinterDrive_v1.1_from_json.xml [--masks <dir>] [--size 3840x2160]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

import numpy as np
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ConversionError(Exception):
    pass


def coco_names() -> dict[int, str]:
    sys.path.insert(0, str(PROJECT_ROOT / "task_models"))
    from labels import COCO_label_map
    return {v: k for k, v in COCO_label_map.items()}


def _bridge(polys: list[np.ndarray]) -> np.ndarray:
    """Join polygons into one by zero-width bridges (largest first; each next one attached at its nearest vertex
    pair): the outline goes out along a bridge, around the region and back, so the fill covers every region."""
    out = polys[0]
    for q in polys[1:]:
        d = ((out[:, None, :] - q[None, :, :]) ** 2).sum(-1)
        i, j = np.unravel_index(int(d.argmin()), d.shape)
        q = np.roll(q, -j, axis=0)
        out = np.concatenate([out[:i + 1], q, q[:1], out[i:]])
    return out


def mask_polygon(m: np.ndarray, offset: tuple[int, int], epsilon: float,
                 regions: str = "all") -> tuple[np.ndarray | None, int, float]:
    """Binary mask crop m (uint8 0/1) at (x0, y0) -> (polygon points (N, 2) in frame pixels or None, number of
    regions, share of mask pixels outside the polygon). regions: all = every region, bridged into one polygon;
    largest = the largest region only."""
    import cv2
    total = int(m.sum())
    if total == 0:
        return None, 0, 0.0
    contours, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = sorted(contours, key=lambda c: (cv2.contourArea(c), len(c)), reverse=True)
    polys = []
    for c in (contours if regions == "all" else contours[:1]):
        if epsilon > 0:
            c = cv2.approxPolyDP(c, epsilon, True)
        pts = c.reshape(-1, 2).astype(float)
        if len(pts) < 3 or cv2.contourArea(pts.astype(np.float32)) == 0:   # a line or a point: its pixel extent
            x0, y0 = pts.min(0)
            x1, y1 = pts.max(0)
            pts = np.array([[x0, y0], [x1 + 1, y0], [x1 + 1, y1 + 1], [x0, y1 + 1]], float)
        polys.append(pts)
    pts = _bridge(polys)
    filled = np.zeros_like(m)
    for q in polys:
        cv2.fillPoly(filled, [np.round(q).astype(np.int32)], 1)
    lost = float(((m == 1) & (filled == 0)).sum()) / total
    return pts + offset, len(contours), lost


def frame_regions(mask_rgb: np.ndarray, colours: list) -> list[tuple[np.ndarray, tuple[int, int]] | None]:
    """Per colour: (binary crop, (x0, y0)) of its pixels in the frame, or None. One pass over the frame."""
    from scipy.ndimage import find_objects
    a = mask_rgb.astype(np.uint32)
    packed = (a[..., 0] << 16) | (a[..., 1] << 8) | a[..., 2]
    codes = [int(c[0]) << 16 | int(c[1]) << 8 | int(c[2]) for c in colours]
    uniq = sorted(set(codes))
    lut = np.zeros(1 << 24, np.uint16)
    lut[uniq] = np.arange(1, len(uniq) + 1)
    lab = lut[packed]
    boxes = find_objects(lab, max_label=len(uniq))
    out = []
    for code in codes:
        i = uniq.index(code) + 1
        sl = boxes[i - 1]
        out.append(None if sl is None else
                   ((lab[sl] == i).astype(np.uint8), (sl[1].start, sl[0].start)))
    return out


def load(json_path: Path) -> tuple[str, dict[int, list[dict]]]:
    data = json.loads(json_path.read_text())
    version = str(data.get("version", ""))
    frames = {}
    for k, v in data.items():
        if k == "version":
            continue
        if not k.isdigit() or int(k) < 1:
            raise ConversionError(f"frame key {k!r}: expected 1, 2, ...")
        frames[int(k)] = v
    if not frames:
        raise ConversionError("no frames")
    return version, frames


def convert(json_path: Path, masks_dir: Path | None, size: tuple[int, int] | None, epsilon: float,
            crowd_attribute: bool, task_name: str, regions: str = "all") -> tuple[str, dict]:
    version, frames = load(json_path)
    n_frames = max(frames)
    names = coco_names()

    if size is None:
        first = sorted(masks_dir.glob("mask_*.png"))[:1] if masks_dir else []
        if not first:
            raise ConversionError("no mask PNGs to take the original size from; give --size WxH")
        size = Image.open(first[0]).size
    w, h = size

    # group objects into tracks: (track_id, occurrence in the frame) -> {frame: object}
    tracks: dict[tuple, dict[int, dict]] = defaultdict(dict)
    report = defaultdict(int)
    renamed = set()
    for fn in sorted(frames):
        seen = defaultdict(int)
        for k, o in enumerate(frames[fn]):
            if "class_id" not in o or not all(c in o for c in ("x_min", "x_max", "y_min", "y_max")):
                raise ConversionError(f"frame {fn} object {k}: needs class_id and x_min, x_max, y_min, y_max")
            tid = o.get("track_id")
            if tid is None:                        # no track id: a track of its own
                key = ("single", fn, k)
            else:
                key = (tid, seen[tid])
                if seen[tid]:
                    report["duplicate_track_id_in_frame"] += 1
                seen[tid] += 1
            tracks[key][fn] = o
            cid = o["class_id"]
            if cid not in names:
                raise ConversionError(f"frame {fn}: class_id {cid} not in task_models/labels.py")
            if o.get("class_name") and o["class_name"] != names[cid]:
                renamed.add((o["class_name"], names[cid]))
    order = sorted(tracks, key=lambda k: (k[0] == "single", k if k[0] != "single" else k[1:]))
    split = defaultdict(list)               # a track whose class changes is split per class
    for key in order:
        by_class = defaultdict(dict)
        for fn, o in tracks[key].items():
            by_class[o["class_id"]][fn] = o
        if len(by_class) > 1:
            report["tracks_split_by_class"] += 1
        for cid in sorted(by_class, key=lambda c: min(by_class[c])):
            split[key].append((cid, by_class[cid]))
    track_list = [t for key in order for t in split[key]]

    any_crowd = any(o.get("iscrowd", 0) for _, objs in track_list for o in objs.values())
    if any_crowd and not crowd_attribute:
        report["crowd_objects_exported_as_normal"] = sum(o.get("iscrowd", 0) for _, objs in track_list
                                                         for o in objs.values())

    # polygons per track: from the JSON, else traced from the masks
    mask_cache: dict[int, np.ndarray | None] = {}

    def mask(fn):
        if fn not in mask_cache:
            mask_cache.clear()                    # frames are visited in order: keep only one
            p = masks_dir / f"mask_{fn:04d}.png" if masks_dir else None
            if p is not None and p.is_file():
                im = Image.open(p).convert("RGB")
                if im.size != (w, h):
                    raise ConversionError(f"{p.name}: size {im.size} != original size {(w, h)}")
                mask_cache[fn] = np.asarray(im)
            else:
                mask_cache[fn] = None
        return mask_cache[fn]

    lost_shares = []
    polys: list[dict[int, np.ndarray]] = []
    # trace polygons frame by frame (one mask PNG decoded once per frame)
    need_trace = defaultdict(list)            # frame -> [(track index, object)]
    for ti, (_, objs) in enumerate(track_list):
        p = {}
        for fn, o in objs.items():
            if o.get("polygon"):
                v = o["polygon"]
                if len(v) < 6 or len(v) % 2:
                    raise ConversionError(f"frame {fn} track {o.get('track_id')}: polygon needs >= 3 x, y pairs")
                p[fn] = np.asarray(v, float).reshape(-1, 2) * [w, h]
                report["polygons_from_json"] += 1
            elif o.get("mask_color") is not None and masks_dir is not None:
                need_trace[fn].append((ti, o))
        polys.append(p)
    for fn in sorted(need_trace):
        m = mask(fn)
        if m is None:
            report["mask_png_missing_objects"] += len(need_trace[fn])
            continue
        found = frame_regions(m, [o["mask_color"] for _, o in need_trace[fn]])
        for (ti, o), r in zip(need_trace[fn], found):
            if r is None:
                report["mask_color_without_pixels"] += 1
                continue
            pts, n_regions, lost = mask_polygon(r[0], r[1], epsilon, regions)
            polys[ti][fn] = pts
            report["polygons_from_masks"] += 1
            if n_regions > 1:
                report["masks_with_several_regions"] += 1
            lost_shares.append(lost)

    # XML
    used = sorted({cid for cid, _ in track_list})
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f+0000")
    crowd_attr = crowd_attribute and any_crowd
    out = ['<?xml version="1.0" encoding="utf-8"?>', "<annotations>", "  <version>1.1</version>", "  <meta>",
           "    <task>", "      <id>0</id>", f"      <name>{escape(task_name)}</name>", f"      <size>{n_frames}</size>",
           "      <mode>interpolation</mode>", "      <overlap>0</overlap>", "      <bugtracker></bugtracker>",
           "      <flipped>False</flipped>", f"      <created>{now}</created>", f"      <updated>{now}</updated>",
           "      <labels>"]
    for cid in used:
        out += ["        <label>", f"          <name>{escape(names[cid])}</name>", "          <attributes>"]
        if crowd_attr:
            out += ["            <attribute>", "              <name>iscrowd</name>",
                    "              <mutable>False</mutable>", "              <input_type>checkbox</input_type>",
                    "              <default_value>false</default_value>",
                    "              <values>false\ntrue</values>", "            </attribute>"]
        out += ["          </attributes>", "        </label>"]
    out += ["      </labels>", "      <segments>", "        <segment>", "          <id>0</id>",
            "          <start>0</start>", f"          <stop>{n_frames - 1}</stop>", "          <url></url>",
            "        </segment>", "      </segments>", "      <owner>", "        <username>admin</username>",
            "        <email></email>", "      </owner>", "      <original_size>", f"        <width>{w}</width>",
            f"        <height>{h}</height>", "      </original_size>", "    </task>", f"    <dumped>{now}</dumped>",
            "  </meta>"]

    def crowd_of(o):
        return bool(o.get("iscrowd", 0)) and crowd_attr

    def shape_lines(tag, fn, geom, outside, crowd):
        f = fn - 1
        if tag == "box":
            g = f'xtl="{geom[0]:.2f}" ytl="{geom[1]:.2f}" xbr="{geom[2]:.2f}" ybr="{geom[3]:.2f}"'
        else:
            g = 'points="' + ";".join(f"{x:.2f},{y:.2f}" for x, y in geom) + '"'
        attr = f'      <attribute name="iscrowd">{"true" if crowd else "false"}</attribute>\n' if crowd_attr else ""
        return (f'    <{tag} frame="{f}" keyframe="1" outside="{int(outside)}" occluded="0" {g} z_order="0">\n'
                f"{attr}    </{tag}>")

    def track_xml(tid, label, tag, shapes: dict[int, tuple], group: int) -> list[str]:
        g = f' group_id="{group}"' if group else ""
        lines = [f'  <track id="{tid}" label={quoteattr(label)} source="file"{g}>']
        fns = sorted(shapes)
        for i, fn in enumerate(fns):
            geom, crowd = shapes[fn]
            lines.append(shape_lines(tag, fn, geom, False, crowd))
            nxt = fn + 1
            if nxt <= n_frames and (i + 1 == len(fns) or fns[i + 1] != nxt):
                lines.append(shape_lines(tag, nxt, geom, True, crowd))     # ends the run
        lines.append("  </track>")
        return lines

    for tid, (cid, objs) in enumerate(track_list):
        shapes = {fn: ((o["x_min"] * w, o["y_min"] * h, o["x_max"] * w, o["y_max"] * h), crowd_of(o))
                  for fn, o in objs.items()}
        out += track_xml(tid, names[cid], "box", shapes, tid + 1)
    tid = len(track_list)
    n_poly_tracks = 0
    for ti, (cid, objs) in enumerate(track_list):
        if polys[ti]:
            out += track_xml(tid, names[cid], "polygon", {fn: (pts, crowd_of(objs[fn])) for fn, pts in polys[ti].items()},
                             ti + 1)
            tid += 1
            n_poly_tracks += 1
    out.append("</annotations>")

    stats = {"version": version, "frames": n_frames, "size": [w, h], "objects": sum(len(v) for v in frames.values()),
             "box_tracks": len(track_list), "polygon_tracks": n_poly_tracks,
             "labels": [names[c] for c in used], "crowd_attribute": crowd_attr, **report,
             "class_name_differs_from_labels_py": sorted(renamed)}
    if lost_shares:
        a = np.asarray(lost_shares)
        stats["traced_mask_pixels_outside_polygon"] = {"mean": round(float(a.mean()), 4),
                                                       "max": round(float(a.max()), 4)}
    return "\n".join(out) + "\n", stats


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("json", type=Path, help="<name>_annotations.json")
    ap.add_argument("--out", type=Path, required=True, help="output XML file")
    ap.add_argument("--masks", type=Path, help="mask folder (default: <name>_masks next to the JSON, if present)")
    ap.add_argument("--size", help="original frame size WxH (default: size of the mask PNGs)")
    ap.add_argument("--epsilon", type=float, default=1.0,
                    help="polygon simplification of traced masks in pixels (default 1.0; 0 = no simplification)")
    ap.add_argument("--regions", choices=("all", "largest"), default="all",
                    help="traced masks with several regions: all = joined into one polygon by zero-width bridges "
                         "(default) | largest = the largest region only")
    ap.add_argument("--no-crowd-attribute", action="store_true",
                    help="export iscrowd objects as normal objects (no 'iscrowd' attribute)")
    ap.add_argument("--task-name", default="imported_from_json", help="<meta><task><name>")
    ap.add_argument("--force", action="store_true", help="overwrite the output file")
    a = ap.parse_args(argv)

    name = a.json.name.removesuffix("_annotations.json")
    masks = a.masks or (a.json.parent / f"{name}_masks")
    masks = masks if masks.is_dir() else None
    if a.masks and masks is None:
        print(f"ERROR: {a.masks} is not a folder", file=sys.stderr)
        return 1
    size = None
    if a.size:
        try:
            size = tuple(int(v) for v in a.size.lower().split("x"))
            assert len(size) == 2 and min(size) > 0
        except (ValueError, AssertionError):
            print(f"ERROR: --size {a.size!r}: expected WxH, e.g. 3840x2160", file=sys.stderr)
            return 1
    if a.out.exists() and not a.force:
        print(f"ERROR: {a.out} exists (use --force to overwrite)", file=sys.stderr)
        return 1
    try:
        xml, st = convert(a.json, masks, size, a.epsilon, not a.no_crowd_attribute, a.task_name, a.regions)
    except ConversionError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(xml)
    print(f"{a.json.name}: version {st['version']!r}, {st['frames']} frames, {st['size'][0]}x{st['size'][1]}, "
          f"{st['objects']} objects, labels {st['labels']}")
    print(f"tracks: {st['box_tracks']} box (ids 0..{st['box_tracks'] - 1}), {st['polygon_tracks']} polygon"
          + (f"; masks: {masks}" if masks else ""))
    for k in ("polygons_from_json", "polygons_from_masks", "masks_with_several_regions",
              "traced_mask_pixels_outside_polygon", "mask_color_without_pixels", "mask_png_missing_objects",
              "duplicate_track_id_in_frame", "tracks_split_by_class", "crowd_objects_exported_as_normal",
              "class_name_differs_from_labels_py"):
        if st.get(k):
            print(f"  {k}: {st[k]}")
    if st["crowd_attribute"]:
        print("NOTE: iscrowd objects carry the attribute 'iscrowd' = true; the CVAT task labels need this checkbox "
              "attribute (or use --no-crowd-attribute)")
    print(f"wrote {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
