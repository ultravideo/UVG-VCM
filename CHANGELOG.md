# Changelog

Changes to the UVG-VCM dataset annotations, newest first. The video sequences are not versioned, only the annotations of each sequence are. Annotation files carry a `"version"` key in the JSON (see [`docs/annotation-formats.md`](docs/annotation-formats.md)). Sequences that are not listed in an entry are unchanged.

## 2026-11-23 Annotation updates

All updated annotations are now  ≥v1.1.

- **CampusView** → v1.1
  - Removed a duplicate box from one frame.
- **CarPark** → v1.1
  - Renamed `CarPark_annotations.json` to `CarPark_lpr_annotations.json`.
  - Added the version key to the JSON.
  - Changed items from plain arrays to objects with named keys (e.g. `{"track_id": 1, "x_min": ..., "plate": "ZPN720"}`).
  - Fixed two tracks.
  - Fixed a few characters.
- **FloorballGame** → v1.1
  - Pose: removed boxes, added areas instead.
  - Refined instance masks.
  - Minor box refinements.
- **HighwayDrive** → v1.1
  - Masks converted from BGR to RGB.
  - Removed objects without masks.
  - Renamed class "mountain-merged" to "rock-merged".
- **HighwayView** → v1.1
  - Masks converted from BGR to RGB.
  - Removed objects without masks.
  - Renamed class "mountain-merged" to "rock-merged".
  - Renamed class "hill" to "grass".
- **KartingTime** → v1.1
  - Renamed `KartingTime_annotations.json` to `KartingTime_bib_annotations.json`.
  - Changed items from plain arrays to objects with named keys.
- **OfficeWalk** → v1.1
  - Refined instance masks.
- **ParkingGarage** → v1.1
  - Renamed `ParkingGarage_annotations.json` to `ParkingGarage_lpr_annotations.json`.
  - Changed items from plain arrays to objects with named keys.
  - Minor character fixes.
- **SyntheticAerial**
  - Renamed `SyntheticAerial_annotations.json` to `SyntheticAerial_obb_annotations.json` (no version change).
- **SyntheticCity** → v1.1
  - Removed zero-size objects.
  - Fixed colour pairings between JSON and masks.
  - Closed the holes in bicycle masks.
- **SyntheticDrone** → v1.1
  - Removed zero-size objects.
  - Fixed colour pairings between JSON and masks.
  - Closed the holes in bicycle masks.
- **TrafficLights** → v1.1
  - Refined instance masks.
  - Refined bounding boxes.
- **WinterDrive** → v1.12
  - Refined instance masks.
  - Refined a few boxes.

## 2026-07-02 Sequences and annotations v1.0

Initial release of the sequences and annotations.

Version exception: the instance masks of the following sequences were version 0.9 in this release: FloorballTrain, FloorballGame, VolleyballGame, WinterDrive, TrafficLights, OfficeWalk.
