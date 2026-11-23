#!/usr/bin/env python3
"""Convert a CVAT "CVAT for video 1.1" XML export into the testbench annotation format.

Output (see docs/annotation-formats.md):
  <out>/<name>_annotations.json   boxes (+ polygons, track_id, mask_color), normalised to [0, 1]
  <out>/<name>_masks/mask_0001.png ...   one RGB mask per frame (only if the XML has polygons)

Rules
- Shapes with outside="1" or occluded="1" are not used; "keyframe" is ignored.
- Boxes and polygons are separate CVAT tracks. A box and a polygon track of the same label in one CVAT group
  (track group_id, as written by json_to_cvat.py) are a pair; a track alone in its group has no partner by
  intent (not an error). Other polygon tracks are paired with the
  box track of the same label that it overlaps best (mean IoU of the box and the polygon extent over their common
  frames, optimal one-to-one assignment). Pairs below --min-pair-iou are not paired. Unpaired tracks are an error
  unless --allow-unpaired is given (then each becomes an object of its own).
- Per frame: box and polygon -> both written; box only -> written without polygon / mask_color (an ignore region
  for instance segmentation); polygon only -> box computed from the polygon extent.
- track_id = 1, 2, ... in box-track order (CVAT track id), then unpaired polygon tracks. mask_color is constant
  per track, from the palette used in the existing annotations ([155,255,255], [255,155,255], ...; the first 63
  colours are those of the existing files, then further brightness levels follow, 4095 colours in total).
- CVAT frame f -> JSON key f + 1 and mask_<f+1:04d>.png (encoder POC 0 = frame 1).
- Masks: RGB PNG at the XML original_size, black background. Overlapping polygons: higher CVAT z_order wins,
  then the object whose box reaches lower in the image (usually nearer to the camera) is drawn on top.
- class_id: the CVAT label must be a COCO name in labels.py, or be mapped with --label-map
  (JSON or YAML {cvat_label: coco_name_or_id}). class_name = the COCO name.
- "iscrowd": 1 if the box or polygon has the attribute iscrowd = true (as written by json_to_cvat.py), else 0. "version" from --version, default from the file name (..._v1.1.xml -> "1.1").

Usage
  python cvat_to_json.py <export>/FloorballGame_v1.1.xml --out <folder> \\
      [--name FloorballGame] [--version 1.1] [--label-map map.yaml]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy.optimize import linear_sum_assignment

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SUPPORTED = {"box", "polygon"}


class ConversionError(Exception):
    pass


# ----------------------------------------------------------------------------- labels and colours

def coco_label_map() -> dict[str, int]:
    sys.path.insert(0, str(PROJECT_ROOT))
    from labels import COCO_label_map
    return dict(COCO_label_map)


def resolve_labels(cvat_labels: set[str], label_map_file: Path | None) -> dict[str, tuple[int, str]]:
    """CVAT label -> (class_id, COCO class_name)."""
    coco = coco_label_map()
    by_id = {v: k for k, v in coco.items()}
    user = {}
    if label_map_file:
        text = label_map_file.read_text()
        if label_map_file.suffix.lower() in (".yaml", ".yml"):
            import yaml
            user = yaml.safe_load(text) or {}
        else:
            user = json.loads(text)
        if not isinstance(user, dict):
            raise ConversionError(f"{label_map_file}: must be a mapping {{cvat_label: coco_name_or_id}}")
    out, bad = {}, []
    for lab in sorted(cvat_labels):
        target = user.get(lab, lab)
        if isinstance(target, int) and target in by_id:
            out[lab] = (target, by_id[target])
        elif isinstance(target, str) and target in coco:
            out[lab] = (coco[target], target)
        else:
            bad.append(f"{lab!r} -> {target!r}")
    if bad:
        raise ConversionError(f"labels not in labels.py: {bad}; use COCO names or --label-map")
    return out


# Each channel takes one of two values from a level pair. The first two pairs give the 63 colours of the existing
# annotation files, in their order; more pairs extend the palette (all values distinct and >= 70, far from black).
LEVEL_PAIRS = [(255, 155), (205, 105), (230, 130), (180, 80), (245, 145), (195, 95), (220, 120), (170, 70)]


def palette() -> list[tuple[int, int, int]]:
    """Mask colours: 63 of the existing annotations first, 4095 unique colours in total."""
    import itertools
    groups = sorted(itertools.product(range(len(LEVEL_PAIRS)), repeat=3),   # pair index per channel (R, G, B)
                    key=lambda t: (max(t), t[2], t[1], t[0]))
    out = []
    for g in groups:
        for c in range(8):              # bit ch of c: channel ch takes the second value of its pair
            col = tuple(LEVEL_PAIRS[g[ch]][c >> ch & 1] for ch in range(3))
            if col != (255, 255, 255):  # white is not used
                out.append(col)
    return out


# ----------------------------------------------------------------------------- XML

def _first(root, *paths):
    for p in paths:
        e = root.find(p)
        if e is not None:
            return e
    return None


def parse_xml(path: Path) -> dict:
    root = ET.parse(path).getroot()
    size = _first(root, "meta/original_size", "meta/task/original_size", "meta/job/original_size")
    if size is None:
        raise ConversionError("no <original_size> in <meta>; cannot normalise coordinates")
    w, h = int(size.findtext("width")), int(size.findtext("height"))
    meta = _first(root, "meta/job", "meta/task")
    start = int(meta.findtext("start_frame", "0")) if meta is not None else 0
    stop = int(meta.findtext("stop_frame")) if meta is not None and meta.findtext("stop_frame") else None
    if stop is None and meta is not None and (meta.findtext("size") or "").strip().isdigit():
        stop = start + int(meta.findtext("size")) - 1          # <task> meta without stop_frame

    if root.findall("image"):
        raise ConversionError("this XML is a 'CVAT for images' export; export as 'CVAT for video 1.1'")
    tracks, skipped, rotated = [], {}, 0
    for t in root.findall("track"):
        shapes = {}
        kinds = set()
        for s in t:
            kinds.add(s.tag)
            if s.tag not in SUPPORTED:
                skipped[s.tag] = skipped.get(s.tag, 0) + 1
                continue
            if s.get("outside") == "1" or s.get("occluded") == "1":
                continue
            if float(s.get("rotation", "0") or 0) != 0:
                rotated += 1
            f = int(s.get("frame"))
            if f in shapes:
                raise ConversionError(f"track {t.get('id')}: two shapes in frame {f}")
            if s.tag == "box":
                geom = [float(s.get(k)) for k in ("xtl", "ytl", "xbr", "ybr")]
            else:
                geom = np.array([[float(v) for v in p.split(",")] for p in s.get("points").split(";")])
            crowd = (s.findtext("attribute[@name='iscrowd']") or "").strip().lower() in ("true", "1")
            shapes[f] = (geom, int(s.get("z_order", "0")), crowd)
        kinds &= SUPPORTED
        if len(kinds) > 1:
            raise ConversionError(f"track {t.get('id')} mixes shape types {sorted(kinds)}")
        if kinds:
            tracks.append({"id": int(t.get("id")), "label": t.get("label"), "kind": kinds.pop(), "shapes": shapes,
                           "group": int(t.get("group_id") or 0)})
    if rotated:
        raise ConversionError(f"{rotated} rotated boxes found; rotation is not supported")
    if stop is None:
        stop = max((f for tr in tracks for f in tr["shapes"]), default=start)
    return {"width": w, "height": h, "start": start, "stop": stop, "tracks": tracks, "skipped": skipped}


# ----------------------------------------------------------------------------- pairing

def poly_extent(pts: np.ndarray) -> list[float]:
    return [float(pts[:, 0].min()), float(pts[:, 1].min()), float(pts[:, 0].max()), float(pts[:, 1].max())]


def iou(a, b) -> float:
    iw = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    ih = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = iw * ih
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def pair_tracks(tracks: list[dict], min_iou: float) -> tuple[list[tuple], list[str]]:
    """[(box_track | None, polygon_track | None, mean_iou)], report lines."""
    boxes = sorted((t for t in tracks if t["kind"] == "box"), key=lambda t: t["id"])
    polys = sorted((t for t in tracks if t["kind"] == "polygon"), key=lambda t: t["id"])
    pairs, used_b, used_p, report = [], set(), set(), []
    # explicit pairs first: one box and one polygon track of the same label in a CVAT group (group_id)
    groups = {}
    for t in boxes + polys:
        if t["group"]:
            groups.setdefault(t["group"], []).append(t)
    for g, ts in sorted(groups.items()):
        if len(ts) == 1:                    # alone in its group: intentionally without a partner
            t = ts[0]
            pairs.append((t, None, None) if t["kind"] == "box" else (None, t, None))
            (used_b if t["kind"] == "box" else used_p).add(t["id"])
            report.append(f"  {t['label']}: {t['kind']} track {t['id']} alone in group {g} (no partner)")
        elif (len(ts) == 2 and {t["kind"] for t in ts} == {"box", "polygon"} and ts[0]["label"] == ts[1]["label"]):
            b, p = sorted(ts, key=lambda t: t["kind"])
            pairs.append((b, p, None))
            used_b.add(b["id"])
            used_p.add(p["id"])
            report.append(f"  {b['label']}: box track {b['id']} <-> polygon track {p['id']}  group {g}")
    for label in sorted({t["label"] for t in tracks}):
        bl = [t for t in boxes if t["label"] == label and t["id"] not in used_b]
        pl = [t for t in polys if t["label"] == label and t["id"] not in used_p]
        if not bl or not pl:
            continue
        score = np.zeros((len(bl), len(pl)))
        for i, b in enumerate(bl):
            for j, p in enumerate(pl):
                common = set(b["shapes"]) & set(p["shapes"])
                if common:
                    score[i, j] = np.mean([iou(b["shapes"][f][0], poly_extent(p["shapes"][f][0])) for f in common])
        rows, cols = linear_sum_assignment(-score)
        for i, j in zip(rows, cols):
            if score[i, j] >= min_iou:
                pairs.append((bl[i], pl[j], float(score[i, j])))
                used_b.add(bl[i]["id"])
                used_p.add(pl[j]["id"])
                second = np.partition(score[i], -2)[-2] if len(pl) > 1 else 0.0
                report.append(f"  {label}: box track {bl[i]['id']} <-> polygon track {pl[j]['id']}  "
                              f"mean IoU {score[i, j]:.3f} (next best {second:.3f})")
    for b in boxes:
        if b["id"] not in used_b:
            pairs.append((b, None, None))
            report.append(f"  {b['label']}: box track {b['id']} has no polygon track")
    for p in polys:
        if p["id"] not in used_p:
            pairs.append((None, p, None))
            report.append(f"  {p['label']}: polygon track {p['id']} has no box track")
    # box-track order first, then polygon-only tracks
    pairs.sort(key=lambda x: (x[0] is None, x[0]["id"] if x[0] else x[1]["id"]))
    return pairs, report


# ----------------------------------------------------------------------------- output

def _num(v: float) -> str:
    return f"{min(max(v, 0.0), 1.0):.6f}"


def write_json(path: Path, version: str, frames: dict[int, list[dict]]) -> None:
    """Same layout as the existing annotation files: one key per line, lists on one line."""
    lines = ["{", f'  "version": {json.dumps(version)},']
    keys = sorted(frames)
    for n, fn in enumerate(keys):
        objs = frames[fn]
        end = "," if n < len(keys) - 1 else ""
        if not objs:
            lines.append(f'  "{fn}": []{end}')
            continue
        lines.append(f'  "{fn}": [')
        for k, o in enumerate(objs):
            body = [f'      "class_name": {json.dumps(o["class_name"])}',
                    f'      "class_id": {o["class_id"]}',
                    f'      "track_id": {o["track_id"]}',
                    f'      "iscrowd": {o["iscrowd"]}']
            if "mask_color" in o:
                body.append(f'      "mask_color": [{",".join(str(c) for c in o["mask_color"])}]')
            body += [f'      "x_min": {_num(o["box"][0])}', f'      "y_min": {_num(o["box"][1])}',
                     f'      "x_max": {_num(o["box"][2])}', f'      "y_max": {_num(o["box"][3])}']
            if "polygon" in o:
                body.append(f'      "polygon": [{",".join(_num(v) for v in o["polygon"])}]')
            lines.append("    {")
            lines.append(",\n".join(body))
            lines.append("    }" + ("," if k < len(objs) - 1 else ""))
        lines.append(f"  ]{end}")
    lines.append("}")
    path.write_text("\n".join(lines) + "\n")


def convert(xml: Path, out: Path, name: str, version: str, label_map: Path | None, min_iou: float,
            allow_unpaired: bool, force: bool, masks: bool) -> dict:
    data = parse_xml(xml)
    w, h = data["width"], data["height"]
    labels = resolve_labels({t["label"] for t in data["tracks"]}, label_map)
    pairs, report = pair_tracks(data["tracks"], min_iou)
    unpaired = [r for r in report if "has no" in r]
    has_polygons = any(t["kind"] == "polygon" for t in data["tracks"])
    if unpaired and has_polygons and not allow_unpaired:
        raise ConversionError("unpaired tracks (use --allow-unpaired to keep them as separate objects):\n"
                              + "\n".join(unpaired))
    colours = palette()
    if has_polygons and len(pairs) > len(colours):
        raise ConversionError(f"{len(pairs)} objects but only {len(colours)} mask colours")

    json_path = out / f"{name}_annotations.json"
    mask_dir = out / f"{name}_masks"
    if not force and (json_path.exists() or (mask_dir.exists() and any(mask_dir.iterdir()))):
        raise ConversionError(f"{json_path} or {mask_dir} already exists (use --force to overwrite)")

    frames: dict[int, list[dict]] = {f + 1: [] for f in range(data["start"], data["stop"] + 1)}
    counts = {"box_and_polygon": 0, "box_only": 0, "polygon_only": 0}
    for tid, (bt, pt, _) in enumerate(pairs, start=1):
        label = (bt or pt)["label"]
        cid, cname = labels[label]
        colour = list(colours[tid - 1]) if has_polygons else None
        fs = set(bt["shapes"] if bt else {}) | set(pt["shapes"] if pt else {})
        for f in sorted(fs):
            b = bt["shapes"].get(f) if bt else None
            p = pt["shapes"].get(f) if pt else None
            o = {"class_name": cname, "class_id": cid, "track_id": tid,
                 "iscrowd": int(any(s is not None and s[2] for s in (b, p)))}
            if p is not None:
                pts = p[0]
                o["mask_color"] = colour
                o["polygon"] = [v for x, y in pts for v in (x / w, y / h)]
                o["_pts"], o["_z"] = pts, p[1]
            box = b[0] if b is not None else poly_extent(p[0])
            o["box"] = [box[0] / w, box[1] / h, box[2] / w, box[3] / h]
            o.setdefault("_z", b[1] if b is not None else 0)
            counts["box_and_polygon" if b is not None and p is not None else
                   "box_only" if b is not None else "polygon_only"] += 1
            frames.setdefault(f + 1, []).append(o)

    out.mkdir(parents=True, exist_ok=True)
    write_json(json_path, version, frames)

    empty_masks = []
    if has_polygons and masks:
        mask_dir.mkdir(exist_ok=True)
        for fn, objs in frames.items():
            im = Image.new("RGB", (w, h))
            draw = ImageDraw.Draw(im)
            for o in sorted((o for o in objs if "_pts" in o), key=lambda o: (o["_z"], o["box"][3])):
                draw.polygon([tuple(pt) for pt in o["_pts"]], fill=tuple(o["mask_color"]))
            im.save(mask_dir / f"mask_{fn:04d}.png")
            a = np.asarray(im).astype(np.int32)
            present = set(np.unique((a[..., 0] << 16) | (a[..., 1] << 8) | a[..., 2]).tolist())
            empty_masks += [(fn, o["track_id"]) for o in objs if "_pts" in o
                            and (o["mask_color"][0] << 16 | o["mask_color"][1] << 8 | o["mask_color"][2]) not in present]
    return {"frames": len(frames), "objects": sum(len(v) for v in frames.values()), "tracks": len(pairs),
            "counts": counts, "pairing": report, "skipped_shapes": data["skipped"], "size": [w, h],
            "labels": {k: list(v) for k, v in labels.items()}, "empty_masks": empty_masks,
            "json": str(json_path), "masks": str(mask_dir) if has_polygons and masks else None}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("xml", type=Path, help="CVAT for video 1.1 XML export")
    ap.add_argument("--out", type=Path, required=True, help="output folder")
    ap.add_argument("--name", help="sequence real name (default: XML file name before '_v<version>')")
    ap.add_argument("--version", help='JSON "version" (default: from the file name, e.g. _v1.1 -> "1.1")')
    ap.add_argument("--label-map", type=Path, help="JSON/YAML {cvat_label: coco_name_or_id}")
    ap.add_argument("--min-pair-iou", type=float, default=0.3, help="minimum mean IoU to pair box/polygon tracks")
    ap.add_argument("--allow-unpaired", action="store_true", help="keep unpaired tracks as separate objects")
    ap.add_argument("--no-masks", action="store_true", help="do not write mask PNGs")
    ap.add_argument("--force", action="store_true", help="overwrite existing output")
    a = ap.parse_args(argv)

    m = re.match(r"(.+?)_v(\d+(?:\.\d+)*)$", a.xml.stem)
    name = a.name or (m.group(1) if m else a.xml.stem)
    version = a.version if a.version is not None else (m.group(2) if m else "")
    try:
        r = convert(a.xml, a.out, name, version, a.label_map, a.min_pair_iou, a.allow_unpaired, a.force,
                    not a.no_masks)
    except ConversionError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    print(f"{a.xml.name}: {r['size'][0]}x{r['size'][1]}, {r['frames']} frames, {r['tracks']} tracks, "
          f"{r['objects']} objects, version {version!r}")
    print("labels: " + ", ".join(f"{k} -> {v[1]} ({v[0]})" for k, v in r["labels"].items()))
    print("pairing:\n" + "\n".join(r["pairing"]))
    print(f"objects: {r['counts']}")
    if r["skipped_shapes"]:
        print(f"WARNING: unsupported shapes ignored: {r['skipped_shapes']}")
    if r["empty_masks"]:
        print(f"WARNING: {len(r['empty_masks'])} polygons cover no pixel in the mask (fully hidden or degenerate): "
              f"{r['empty_masks'][:10]}")
    print(f"wrote {r['json']}" + (f" and {r['masks']}/" if r["masks"] else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
