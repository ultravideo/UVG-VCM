# UVG-VCM

**Benchmarking dataset for machine-oriented visual data compression**

[![License: CC BY 4.0](https://img.shields.io/badge/data%20license-CC%20BY%204.0-lightgrey.svg)](https://creativecommons.org/licenses/by/4.0/)
[![Code license: BSD 3-Clause Clear](https://img.shields.io/badge/code%20license-BSD--3--Clause--Clear-lightgrey.svg)](LICENSE)
[![Paper DOI](https://img.shields.io/badge/DOI-10.1109%2FQoMEX69967.2026.11618360-blue.svg)](https://doi.org/10.1109/QoMEX69967.2026.11618360)

UVG-VCM is an open dataset of uncompressed, densely annotated video sequences, built for evaluating video codecs for machine vision, i.e. **Video Coding for Machines (VCM)** and **Feature Coding for Machines (FCM)**. It was created by the [Ultra Video Group](https://ultravideo.fi) at Tampere University.

<!-- TODO: add a preview image or short collage of sequence thumbnails: assets/preview.png -->

## Highlights

- **20 uncompressed video sequences**, 70 to 1140 frames each (10,930 frames in total). The sources are real-world camera captures plus synthetic content.
- **High-fidelity sources:** 15 real-world sequences are 4K (3840×2160), 60 fps, 16-bit YUV 4:4:4. There are also 3 synthetic 4K sequences (8-bit YUV 4:4:4) and 2 Full HD stereo-camera sequences (8-bit YUV 4:2:2).
- **Multiple machine vision tasks:** object detection, oriented object detection, object tracking, instance segmentation, semantic segmentation, panoptic segmentation, human pose estimation, depth estimation, license-plate recognition and race bib recognition.
- **Diverse, realistic scenarios:** surveillance, autonomous driving and sailing, sports analytics, parking management, robotics, and aerial/drone views.
- **Open license:** videos and annotations are released under CC BY 4.0.

## Download

The videos and annotations are hosted on the dataset website, not in this repository:

**➡️ <https://ultravideo.fi/UVG-VCM/>**

<!-- TODO: total download size, file naming/layout of the video files (e.g. .yuv / .y4m), checksum file location -->
<!-- TODO: link or command for the download script in scripts/ once it exists -->

## Sequences

Click a sequence name column for details in [`sequences.csv`](sequences.csv), which also includes capture source and per-frame object detection instance counts (min / max / avg).

| Sequence | Resolution | Format | FPS | Frames | Use case | Env. | Camera | Tasks |
|---|---|---|---|---|---|---|---|---|
| HighwayView | 3840×2160 | YUV444, 16-bit | 60 | 600 | Surveillance | Outdoor | Static | DET, TRK, INS, SPS |
| FloorballTrain | 3840×2160 | YUV444, 16-bit | 60 | 600 | Sports analytics | Indoor | Static | DET, TRK, INS |
| FloorballGame | 3840×2160 | YUV444, 16-bit | 60 | 420 | Sports analytics | Indoor | Panning | DET, TRK, INS, HPE |
| SpotRobot | 3840×2160 | YUV444, 16-bit | 60 | 600 | Robot | Indoor | Moving | DET, TRK |
| VolleyballGame | 3840×2160 | YUV444, 16-bit | 60 | 600 | Sports analytics | Indoor | Static | DET, TRK, INS |
| WinterDrive | 3840×2160 | YUV444, 16-bit | 60 | 600 | Autonomous driving | Outdoor | Moving | DET, TRK, INS |
| HighwayDrive | 3840×2160 | YUV444, 16-bit | 60 | 600 | Autonomous driving | Outdoor | Moving | DET, TRK, INS, SPS |
| TrafficLights | 3840×2160 | YUV444, 16-bit | 60 | 600 | Autonomous driving | Outdoor | Moving | DET, TRK, INS |
| OfficeWalk | 3840×2160 | YUV444, 16-bit | 60 | 600 | Bodycam/robot | Indoor | Moving | DET, TRK, INS |
| BoatReverse | 3840×2160 | YUV444, 16-bit | 60 | 300 | Autonomous sailing | Outdoor | Moving | DET, TRK, INS |
| CampusView | 3840×2160 | YUV444, 16-bit | 60 | 600 | Surveillance | Outdoor | Panning | DET, TRK |
| JobFair | 3840×2160 | YUV444, 16-bit | 60 | 600 | Surveillance | Indoor | Static | DET, TRK |
| CarPark | 3840×2160 | YUV444, 16-bit | 60 | 600 | Parking management | Outdoor | Static | LPR |
| ParkingGarage | 3840×2160 | YUV444, 16-bit | 60 | 1140 | Parking management | Both | Static | LPR |
| KartingTime | 3840×2160 | YUV444, 16-bit | 60 | 70 | Sports analytics | Outdoor | Static | BIB |
| UnderPark | 1920×1080 | YUV422, 8-bit | 30 | 300 | Autonomous driving | Indoor | Moving | DEP |
| AuditoriumWalk | 1920×1080 | YUV422, 8-bit | 30 | 300 | Bodycam/robot | Indoor | Moving | DEP |
| SyntheticAerial | 3840×2160 | YUV444, 8-bit | 60 | 600 | Aerial (synthetic) | Outdoor | Moving | OR-DET |
| SyntheticDrone | 3840×2160 | YUV444, 8-bit | 60 | 600 | Drone (synthetic) | Outdoor | Moving | DET, TRK, INS |
| SyntheticCity | 3840×2160 | YUV444, 8-bit | 60 | 600 | Surveillance (synthetic) | Outdoor | Static | DET, TRK, INS |

**Task abbreviations:** DET = object detection, TRK = tracking, INS = instance segmentation, SPS = semantic and panoptic segmentation, HPE = human pose estimation, LPR = license-plate recognition (detection + OCR), BIB = race bib recognition (detection + OCR), DEP = depth estimation, OR-DET = oriented object detection.

**Capture sources:** real-world sequences were captured with a Blackmagic Micro Studio 4K G2 camera (Panasonic LUMIX G H-FS12060 lens), depth sequences with a Stereolabs ZED 2i stereo camera, and synthetic sequences were generated with the [CiThruS2](https://github.com/ultravideo/CiThruS2) simulation platform. <!-- TODO: verify CiThruS2 link -->

## Annotations

All annotations are stored per sequence as JSON files (plus PNG masks for segmentation and depth), with coordinates normalised to [0, 1] and objects keyed by frame number. Segmentation and depth use PNG files.

| Task | Files |
|---|---|
| Object detection, tracking, instance segmentation | `<name>_annotations.json` + `<name>_masks/` |
| Semantic / panoptic segmentation | `<name>_panoptic_annotations.json` + `<name>_panoptic_masks/` |
| Human pose estimation | `<name>_pose_annotations.json` |
| Oriented object detection | `<name>_obb_annotations.json` |
| License-plate recognition | `<name>_lpr_annotations.json` |
| Race bib recognition | `<name>_bib_annotations.json` |
| Depth estimation | `<name>_depth/`: one 16-bit grayscale PNG per frame, millimetres |

Class labels follow the COCO taxonomy (detection, tracking, segmentation, pose) and DOTA (oriented detection). Objects have persistent IDs across frames. The format is specified in [`docs/annotation-formats.md`](docs/annotation-formats.md).


## Benchmarking

<!-- TODO: link to testbench repo -->
A complete testbench for running codec evaluations on UVG-VCM is available in a separate repository: **Coming soon**.

The baseline results in the paper follow JVET CTC-style procedures: sequences were coded with the VVC Test Model (VTM v23.3) in random access configuration, QP 24 to 56, and evaluated on object detection with a Faster R-CNN X101-FPN model.

## Repository contents

| Folder / file | Description |
|---|---|
| [`sequences.csv`](sequences.csv) | Machine-readable sequence metadata |
| [`scripts/`](scripts/) | General-purpose scripts (download, checksum verification, utilities) |
| [`annotation/`](annotation/) | Converters between CVAT XML and the released JSON/mask annotations, plus workflow instructions. Contains tooling only; the annotations themselves are downloaded from the website. |
| [`docs/`](docs/) | Annotation format specifications |
| [`CHANGELOG.md`](CHANGELOG.md) | Dataset and repository change history |

## Contributing

Community refinement of the annotations is welcome. If you find an annotation error, please open an issue; to propose fixes, see the workflow in [`annotation/`](annotation/). <!-- TODO: contribution guidelines, e.g. CONTRIBUTING.md -->

## License

- **Dataset (videos and annotations):** [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)
- **Code in this repository:** [BSD 3-Clause Clear](LICENSE)

## Citation

If you use UVG-VCM, please cite:

```bibtex
@inproceedings{partanen_uvg-vcm_2026,
	address = {Cardiff, United Kingdom},
	title = {{UVG}-{VCM}: {Benchmarking} {Dataset} for {Machine}-{Oriented} {Visual} {Data} {Compression}},
	isbn = {979-8-3195-0032-8},
	doi = {10.1109/QoMEX69967.2026.11618360},
	booktitle = {2026 18th {International} {Conference} on {Quality} of {Multimedia} {Experience} ({QoMEX})},
	publisher = {IEEE},
	author = {Partanen, Tero and Anttila, Miro and Kortelahti, Rudolf and Gautier, Guillaume and Mercat, Alexandre and Vanne, Jarno},
	month = jun,
	year = {2026},
}
```
