# Annotation formats

Annotations are stored per sequence in `<annotations_root>/<name>/`, where `<name>` is the sequence name (e.g. `VolleyballGame`). This page defines the file formats; the converters between CVAT XML and these formats are in [`../annotation/`](../annotation/).

## Common conventions

- **One JSON file per task**, named `<name>_<task>_annotations.json`. Objects are grouped by frame number. Keys are frame numbers as strings, starting from `"1"`, and each value is a list of objects (an empty list for frames without objects). An optional top-level `"version"` key may be present.
- **Coordinates are normalised to [0, 1]** relative to the frame width (x) and height (y). Multiply by the frame size to get pixels.
- **`iscrowd`** is optional everywhere; a missing value means 0.
- **Persistent IDs:** `track_id` identifies the same object across frames.
- **Informative fields:** `class_name` is for readability only. Metrics use `class_id`.

| Task | File | Key fields |
|---|---|---|
| Detection, tracking, instance segmentation | `<name>_annotations.json` | `class_id`, box, `track_id`, `polygon`, `mask_color` |
| Semantic / panoptic segmentation | `<name>_panoptic_annotations.json` | `class_id`, `mask_color`, `track_id` (segment id) |
| Pose | `<name>_pose_annotations.json` | `keypoints`, `area` |
| Oriented detection | `<name>_obb_annotations.json` | `class_id`, `bbox` (4 corners) |
| License plate | `<name>_lpr_annotations.json` | `track_id`, box, `plate` |
| Race bib | `<name>_bib_annotations.json` | `track_id`, box, `bib` |
| Depth | `<name>_depth/*.png` | 16-bit PNG, millimetres |

Boxes use the keys `x_min`, `x_max`, `y_min`, `y_max`.

## Detection, tracking and instance segmentation

`<name>_annotations.json`. Class ids are the contiguous COCO detection ids (e.g. person = 1, car = 3, stop sign = 12). `track_id`, `polygon` and `mask_color` are optional.

- `polygon`: instance mask outline as a flat list `[x1, y1, x2, y2, ...]`, normalised to [0, 1].
- `mask_color`: `[R, G, B]` colour of this instance in the frame's mask PNG (see [Masks](#masks)).

```json
{
  "version": "1.0",
  "1": [
    {"class_id": 1, "x_min": 0.562984, "x_max": 0.62898, "y_min": 0.54725, "y_max": 0.78412,
     "track_id": 7, "iscrowd": 0, "mask_color": [155, 155, 155]}
  ],
  "2": []
}
```

## Semantic and panoptic segmentation

`<name>_panoptic_annotations.json`, with masks in `<name>_panoptic_masks/`. Each entry is one segment of the frame.

- `class_id` uses the official **COCO panoptic category ids** (133 categories): 80 *things* with the original COCO ids 1..90 (with gaps) and 53 *stuff* classes with ids 92..200 (e.g. 149 road, 184 tree-merged). Note that these differ from the contiguous ids of the detection JSON for classes after "fire hydrant" (stop sign is 13 here, 12 there).
- `mask_color` is **required**. `track_id` (segment id), `class_name` and the box are informative only.
- Things are countable instances; stuff classes are amorphous regions with one segment per class and frame.
- Panoptic masks do not overlap and need not equal the instance masks (an object partly behind a fence loses those pixels to the fence).
- **Semantic segmentation** uses the same annotations, with all segments of a class merged into a per-pixel class label.

```json
{"class_name": "road", "class_id": 149, "track_id": 29, "mask_color": [155, 205, 155],
 "x_min": 0.0, "y_min": 0.30, "x_max": 1.0, "y_max": 1.0}
```

## Masks

Instance masks are in `<name>_masks/` and panoptic masks in `<name>_panoptic_masks/`. There is one PNG per frame, named `mask_0001.png`, `mask_0002.png`, and so on, in RGB or RGBA (alpha is ignored). Pixel colours are in RGB order and match `mask_color` in the JSON. Colours not used by any object in that frame are background (instance masks) or unlabelled/void (panoptic masks, ignored by the metrics).

## Pose

`<name>_pose_annotations.json`. Each entry is one person; no bounding box is needed.

- `class_id`: 1 (person).
- `keypoints`: 51 values, the 17 COCO keypoints in COCO order as `x, y, v`. `x`, `y` are normalised (a point may lie slightly outside the image). `v`: 0 = not labelled (x, y ignored), 1 = labelled but occluded, 2 = labelled and visible. "Left" is the person's own left.
- `area`: segmentation area as a fraction of the image area (COCO `area` normalised). Scale by W × H for the OKS in COCO keypoint AP.

```json
{"class_id": 1, "area": 0.022333, "keypoints": [0.196602, 0.251574, 0, 0.190203, 0.241269, 0, "...", 0.161966, 0.595815, 2]}
```

## Oriented object detection

`<name>_obb_annotations.json`.

- `class_id`: DOTA v1.0 category id, **0-based**: 0 plane, 1 ship, 2 storage tank, 3 baseball diamond, 4 tennis court, 5 basketball court, 6 ground track field, 7 harbor, 8 bridge, 9 large vehicle, 10 small vehicle, 11 helicopter, 12 roundabout, 13 soccer ball field, 14 swimming pool.
- `bbox`: the four corners `[[x, y], ...]` of the rotated box, normalised (any start corner and direction). Corners may lie outside [0, 1] for objects cut by the frame edge (full object extent).

```json
{"class_id": 10, "bbox": [[0.71267, 0.977583], [0.727843, 0.97683], [0.728052, 0.990084], [0.712878, 0.990837]]}
```

## License plate and race bib recognition

`<name>_lpr_annotations.json` and `<name>_bib_annotations.json` share one layout: `track_id` (one id per physical plate or competitor), the axis-aligned box, and the text visible in that frame in `plate` or `bib`. A partly visible plate or bib contains only its visible characters (e.g. `"48"` of `HTI748`; `"15"` of `156`). Bib boxes cover the full bib, even when partly hidden.

```json
{"track_id": 1, "x_min": 0.490664, "x_max": 0.505586, "y_min": 0.428843, "y_max": 0.436329, "plate": "ZPN720"}
```

## Depth

Depth ground truth is in `<annotations_root>/<name>/<name>_depth/`. There is no JSON file, and a sequence may have only this folder. One PNG per frame:

- **Names:** `<stem>_NNNN.png` (or `_NNN`), e.g. `depth_0001.png` ... `depth_0600.png`. The number is the 1-based frame number, matching the decoded frames and the JSON frame keys, and all files share one stem.
- **Values:** 16-bit grayscale, single channel. The pixel value is the metric depth in millimetres (1..65535 mm, up to 65.5 m). **0 = no depth** (invalid pixel). Invalid pixels are ignored by the metrics.
- **Size:** may differ from the video frames; the testbench resizes with nearest neighbour to the frame size, so keep the video aspect ratio.
- **Scoring:** frames with a depth PNG are scored, and each must have a decoded frame. Decoded frames without a depth PNG are not scored.

Example: `UnderPark_depth/depth_0001.png` ... `depth_0600.png`, 1920×1080, ZED 2i depth in millimetres (densified).
