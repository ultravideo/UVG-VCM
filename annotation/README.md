# Annotation tooling

This folder contains **tooling only**: scripts and instructions for converting between [CVAT](https://github.com/cvat-ai/cvat) XML and the released UVG-VCM annotation files. The annotations themselves are downloaded from the [dataset website](https://ultravideo.fi/UVG-VCM/). The released formats are specified in [`../docs/annotation-formats.md`](../docs/annotation-formats.md).

The converters let you open released annotations in CVAT, refine them, and export them back to the released format, which is the workflow for community-driven annotation refinement.

<!-- TODO: CVAT version used for the annotations and tested with these scripts -->

## Contents

| File | Purpose |
|---|---|
| `json_to_cvat.py` | Released JSON + masks → CVAT XML ("CVAT for video 1.1") |
| `cvat_to_json.py` | CVAT XML ("CVAT for video 1.1" export) → released JSON + masks |
| `examples/` | Small sample files for trying the converters <!-- TODO --> |

The converters cover **object detection, tracking and instance segmentation** (`<name>_annotations.json` and `<name>_masks/`). Other tasks (panoptic and semantic segmentation, pose, oriented detection, license plates, race bibs) are not yet supported.

<!-- TODO: Python dependencies (e.g. numpy, opencv-python, PyYAML) -->

## Workflow

1. **Convert** the released annotations of a sequence to CVAT XML with `json_to_cvat.py`.
2. **Import** the XML into a CVAT task for the same sequence and refine the annotations. The task's labels must match the COCO class names; to keep crowd labels, add a checkbox attribute `iscrowd` to the labels.
3. **Export** the task from CVAT as "CVAT for video 1.1" XML.
4. **Convert** the exported XML back to the released format with `cvat_to_json.py`.
5. **Submit** your refined annotations: <!-- TODO: describe how, e.g. open an issue / pull request, what to include -->

## Released → CVAT (`json_to_cvat.py`)

```bash
python annotation/json_to_cvat.py <name>/<name>_annotations.json \
    --out <name>_v1.1_from_json.xml [--masks <dir>] [--size 3840x2160]
```

Output is one CVAT XML file with a minimal task section (size, labels, one segment).

- **Tracks:** each JSON `track_id` becomes a box track. Each object that has a polygon also gets a polygon track. A box track and its polygon track share a CVAT group, which `cvat_to_json.py` uses to pair them again.
- **Polygons:** the JSON `polygon` is used when present. Otherwise, if the object has a `mask_color` and the masks folder exists, the polygon is traced from its mask (outer outline of each connected region, simplified with `--epsilon`). Holes are filled. A CVAT track has one polygon per frame, so an object split into several regions (e.g. by an occluder) is joined into one polygon (`--regions all`, default) or only the largest region is kept (`--regions largest`).
- **Frames:** JSON key `"1"` becomes CVAT frame 0. Every shape is a keyframe. Where a track is absent (a gap, or after its last frame), an *outside* shape ends it so CVAT does not interpolate across the gap.
- **Coordinates:** normalised coordinates are converted to pixels at the original size (`--size`, default: the size of the mask PNGs).
- **Labels:** the COCO name of `class_id`.
- **`iscrowd`:** objects with `iscrowd = 1` get the label attribute `iscrowd = true`. The CVAT task must define this attribute on the label, otherwise use `--no-crowd-attribute` (the objects are then exported as normal objects).
- A `track_id` that occurs twice in one frame puts the second object on an extra track (reported by the script).

| Option | Effect |
|---|---|
| `--out` | Output XML file |
| `--masks` | Masks folder (default: `<name>_masks/` next to the JSON) <!-- TODO: confirm default --> |
| `--size WxH` | Original frame size in pixels |
| `--epsilon` | Polygon simplification when tracing masks, in pixels (0 = every boundary pixel) |
| `--regions` | `all` (default) or `largest`, for objects with several mask regions |
| `--no-crowd-attribute` | Do not write the `iscrowd` attribute |

Not carried into the XML: track ids and mask colours (see [Roundtrip behaviour](#roundtrip-behaviour)).

## CVAT → released (`cvat_to_json.py`)

```bash
python annotation/cvat_to_json.py <export>/FloorballGame_v1.1.xml --out <folder> \
    [--name FloorballGame] [--version 1.1] [--label-map map.yaml]
```

Output: `<name>_annotations.json` (boxes, polygons, `track_id`, `mask_color`, normalised to [0, 1]) and `<name>_masks/mask_0001.png`, ... (only if the XML contains polygons).

**Which shapes are used**

- Shapes marked *outside* or *occluded* in CVAT are not used (no instance in that frame). The `keyframe` flag is ignored.
- Boxes and polygons are separate tracks in CVAT. A box track and a polygon track of the same label in one CVAT group (as written by `json_to_cvat.py`) are a pair; a track alone in its group has no partner by intent. Other polygon tracks are paired with the box track of the same label that they overlap best (mean IoU of the box and the polygon extent over their common frames, optimal one-to-one assignment). Pairs below `--min-pair-iou` are not paired. Unpaired tracks are an error unless `--allow-unpaired` is given, in which case each becomes an object of its own.
- Per frame: box and polygon → both written; box only → written without polygon and `mask_color` (an ignore region for instance segmentation); polygon only → the box is computed from the polygon extent.

**Output conventions**

- `track_id` is numbered 1, 2, ... in box-track order (CVAT track id), followed by unpaired polygon tracks.
- `mask_color` is constant per track and taken from a fixed palette (the first 63 colours are those used in the existing annotations, followed by further brightness levels, 4095 in total).
- CVAT frame *f* becomes JSON key *f* + 1 and `mask_<f+1:04d>.png` (the first frame is frame 1).
- Masks are RGB PNGs at the original size of the XML, with a black background. Where polygons overlap, the higher CVAT `z_order` is drawn on top, then the object whose box reaches lower in the image (usually nearer to the camera).
- Coordinates are normalised to [0, 1] with 6 decimals.
- `iscrowd` is 1 if the box or polygon has the attribute `iscrowd = true` (as written by `json_to_cvat.py`), otherwise 0.
- The `version` key comes from `--version`; by default it is read from the file name (`..._v1.1.xml` → `"1.1"`).
- CVAT metadata (task and job information) is not carried over.

**Class labels.** The CVAT label must be a COCO class name, or be mapped with `--label-map` (a JSON or YAML file `{cvat_label: coco_name_or_id}`). `class_id` and `class_name` are taken from the COCO name.

| Option | Effect |
|---|---|
| `--out` | Output folder |
| `--name` | Sequence name used in the output file names |
| `--version` | Version string written to the JSON |
| `--label-map` | Map CVAT labels to COCO class names or ids |
| `--min-pair-iou` | Minimum IoU for pairing tracks that are not in the same CVAT group |
| `--allow-unpaired` | Keep unpaired tracks as separate objects instead of failing |

## Roundtrip behaviour

Converting released annotations to CVAT and back **does not reproduce the original files byte for byte**. Class ids, boxes, polygons, crowd labels and the box/polygon pairing are preserved (coordinates to 6 decimals), but:

- mask images are regenerated from the polygons, and `mask_color` values are reassigned from the palette;
- `track_id` values are renumbered 1, 2, ... in box-track order;
- if an object has no `polygon` in the JSON, its polygon is traced from the mask, which simplifies the outline and fills holes;
- an object with several mask regions in one frame is joined into one polygon (or reduced to its largest region with `--regions largest`);
- shapes marked outside or occluded in CVAT are dropped.

When submitting refinements, expect diffs in the mask files and ids that do not correspond to actual annotation changes. When adding new objects in CVAT, give a box track and its polygon track the same label and the same group, or let them overlap, so that they are paired.
