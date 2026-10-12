# Detector Tuning Report

Generated 2026-10-12 by `scripts/tune_detector.py`.

## Method

- Synthetic eval set: 25 images per defect kind (scratch, dent, spots) plus 75 clean plates, generated with `make_sample_images.generate`, seed `20261012`. Filenames carry the ground-truth defect kind.
- Grid search over `DetectorAgent` thresholds:
  - `defect_contrast`: [25, 40, 55, 70]
  - `min_area`: [40.0, 80.0, 150.0]
  - `hole_circularity`: [0.6, 0.75, 0.9]
- Image-level scoring: a defective image counts as detected when the detector returns at least one detection; label accuracy checks the top detection's label against the ground-truth kind.
- Ranking: `score = mean per-kind detection recall - clean-image false-positive rate`; ties broken by mean label accuracy.

## Full grid results (sorted by score)

| defect_contrast | min_area | hole_circularity | precision | recall | fp_rate | label_acc | score |
|-----------------|----------|------------------|-----------|--------|---------|-----------|-------|
| 40 | 40 | 0.6 | 1.000 | 1.000 | 0.000 | 0.987 | 1.000 |
| 40 | 40 | 0.75 | 1.000 | 1.000 | 0.000 | 0.987 | 1.000 |
| 40 | 80 | 0.6 | 1.000 | 1.000 | 0.000 | 0.987 | 1.000 |
| 40 | 80 | 0.75 | 1.000 | 1.000 | 0.000 | 0.987 | 1.000 |
| 40 | 150 | 0.6 | 1.000 | 0.987 | 0.000 | 0.973 | 0.987 |
| 40 | 150 | 0.75 | 1.000 | 0.987 | 0.000 | 0.973 | 0.987 |
| 55 | 40 | 0.6 | 0.949 | 1.000 | 0.053 | 0.987 | 0.947 |
| 55 | 40 | 0.75 | 0.949 | 1.000 | 0.053 | 0.987 | 0.947 |
| 55 | 80 | 0.6 | 0.949 | 1.000 | 0.053 | 0.987 | 0.947 |
| 55 | 80 | 0.75 | 0.949 | 1.000 | 0.053 | 0.987 | 0.947 |
| 55 | 150 | 0.6 | 0.948 | 0.973 | 0.053 | 0.960 | 0.920 |
| 55 | 150 | 0.75 | 0.948 | 0.973 | 0.053 | 0.960 | 0.920 |
| 40 | 40 | 0.9 | 0.524 | 1.000 | 0.907 | 0.333 | 0.093 |
| 40 | 80 | 0.9 | 0.524 | 1.000 | 0.907 | 0.333 | 0.093 |
| 40 | 150 | 0.9 | 0.524 | 1.000 | 0.907 | 0.333 | 0.093 |
| 70 | 40 | 0.6 | 0.500 | 1.000 | 1.000 | 0.973 | 0.000 |
| 70 | 40 | 0.75 | 0.500 | 1.000 | 1.000 | 0.973 | 0.000 |
| 70 | 80 | 0.6 | 0.500 | 1.000 | 1.000 | 0.973 | 0.000 |
| 70 | 80 | 0.75 | 0.500 | 1.000 | 1.000 | 0.973 | 0.000 |
| 70 | 150 | 0.6 | 0.500 | 1.000 | 1.000 | 0.973 | 0.000 |
| 70 | 150 | 0.75 | 0.500 | 1.000 | 1.000 | 0.973 | 0.000 |
| 55 | 40 | 0.9 | 0.500 | 1.000 | 1.000 | 0.333 | 0.000 |
| 55 | 80 | 0.9 | 0.500 | 1.000 | 1.000 | 0.333 | 0.000 |
| 55 | 150 | 0.9 | 0.500 | 1.000 | 1.000 | 0.333 | 0.000 |
| 70 | 40 | 0.9 | 0.500 | 1.000 | 1.000 | 0.333 | 0.000 |
| 70 | 80 | 0.9 | 0.500 | 1.000 | 1.000 | 0.333 | 0.000 |
| 70 | 150 | 0.9 | 0.500 | 1.000 | 1.000 | 0.333 | 0.000 |
| 25 | 40 | 0.6 | 1.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| 25 | 40 | 0.75 | 1.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| 25 | 40 | 0.9 | 1.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| 25 | 80 | 0.6 | 1.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| 25 | 80 | 0.75 | 1.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| 25 | 80 | 0.9 | 1.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| 25 | 150 | 0.6 | 1.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| 25 | 150 | 0.75 | 1.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| 25 | 150 | 0.9 | 1.000 | 0.000 | 0.000 | 0.000 | 0.000 |

## Defaults vs best config

Best grid config: `defect_contrast=40`, `min_area=40`, `hole_circularity=0.6`.

| config | kind | n | detection recall | label accuracy |
|--------|------|---|------------------|----------------|
| defaults | scratch | 25 | 1.000 | 1.000 |
| defaults | dent | 25 | 1.000 | 0.960 |
| defaults | spots | 25 | 1.000 | 1.000 |
| best | scratch | 25 | 1.000 | 1.000 |
| best | dent | 25 | 1.000 | 0.960 |
| best | spots | 25 | 1.000 | 1.000 |

| config | image precision | image recall | clean fp_rate |
|--------|-----------------|--------------|---------------|
| defaults | 1.000 | 1.000 | 0.000 |
| best | 1.000 | 1.000 | 0.000 |

## Failure modes (measured)

- Dead zone: 9 config(s) with defect_contrast in [25] detect nothing at all. At that loose a threshold the plate's own texture merges into one contour larger than max_area, so the area filter drops it.
- Hole-rejection cliffs: 15 config(s) flag most clean plates (fp_rate >= 0.5). Measured causes: at defect_contrast=70 the mounting-hole bright-ring check misses by under one gray level (ring_mean 208.0 vs bar 208.5), and at hole_circularity=0.9 the real holes (circularity 0.889) fail the circularity bar, so holes get labeled as spots.
- Partial misses: 4 config(s) detect some but not all defects (worst recall 0.973); these are the min_area=150 configs, where the smallest synthetic spots fall below the area bar.

## Recommendation

Keep the current defaults: no grid config beats them on this dataset.
