# Method and Reproducibility Revision Evidence Notes

Branch: `review-method-reproducibility`

Scope: this note documents the manuscript edits made to address reviewer concerns about the modified YOLO claim, dataset construction, split/leakage risk, NDVI-assisted annotation, training adaptations, and threshold terminology.

## Reviewer Concerns Covered

- R2-2: clarify what was modified in YOLO and improve reproducibility.
- R3-10: avoid unsupported claims about an enhanced architecture and explain the study scope instead of adding unverified YOLOv1/YOLOv2/YOLO-NAS baselines.
- R3-11: clarify that the VI variants are input-channel configurations within the same detector family.
- R3-12: add training/testing protocol details where supported by project evidence.
- R3-13: define confidence thresholds used in PR/F1-confidence curves.
- R4-1: describe the sample unit, tiling/cropping assumption, split, and leakage risk.
- R4-2: address NDVI-assisted annotation as a possible validity concern.
- R4-3: acknowledge that robustness to alignment errors and other sensors was not evaluated.

## Manuscript Changes Made

- Replaced broad "modified YOLO" language with a narrower claim: a YOLOv8 instance-segmentation detector adapted to multispectral inputs through the input-channel configuration.
- Rewrote the model subsection as "Model and Training Adaptation" and stated that the backbone and segmentation head follow YOLOv8-seg, with no new detection block introduced.
- Added a reproducibility table covering detector family, implementation, input configurations, training data unit, split, multispectral training adaptation, and evaluation thresholds.
- Clarified that the experiments use a Field 2 subset from late March and early-to-mid April, while the broader campaign was inspected from late February to early June.
- Added a "Dataset Construction and Split" subsection describing one aligned UAV image stack per sample, no additional overlapping patch-generation step after stack generation, annotated-only filtering, 70/15/15 split, and within-field leakage limitations.
- Added text explaining that NDVI was a visual support source during annotation, not an automatic labeling rule, and that NDVI-channel results should be interpreted cautiously.
- Standardized much of the terminology from "models" to "input-channel configurations" when referring to the five-band baseline and VI variants.
- Added limitation text for alignment sensitivity, within-field evaluation, and NDVI-assisted annotation.

## Evidence Map

### Detector input-channel adaptation

- `D:/Research/Weed-backup 2026-01-24/yolov8/yolov8n_custom_seg_ch5.yaml`, lines 1-47, defines a YOLOv8-seg instance-segmentation model with `ch: 5`, `nc: 10`, and the standard-looking YOLOv8 backbone/head structure.
- `D:/Research/Weed-backup 2026-01-24/yolov8/yolov8n_custom_seg_ch6.yaml`, lines 1-47, is the corresponding `ch: 6` configuration with the same backbone/head structure.
- Interpretation: the strongest verified evidence supports an input-channel adaptation, not a new YOLO architecture block. The manuscript now uses this narrower claim.

### Multispectral training adaptation

- `D:/Research/Weed-backup 2026-01-24/yolov8/train_multi.py`, lines 26-34, imports Ultralytics YOLO with multiband support enabled.
- `D:/Research/Weed-backup 2026-01-24/yolov8/train_multi.py`, lines 55-87 and 155-173, show training calls using `device='cuda:0'` and disabled HSV augmentation terms (`hsv_s=0`, `hsv_h=0`, `hsv_v=0`).
- `D:/Research/Weed-backup 2026-01-24/yolov8/train_multi.py`, lines 124-143 and 159-172, show geometric augmentation parameters such as rotation, translation, scaling, shearing, flipping, and mosaic settings.
- Interpretation: it is defensible to state that training was adapted for stacked multispectral arrays and that RGB-specific HSV augmentation was disabled. Exact final hyperparameter reporting should remain cautious unless the final run logs are tied to each submitted result.

### Data selection and date scope

- `D:/Research/Weed-backup 2026-01-24/weed-utility/src/yolo_prep_dataset.py`, lines 35-40 and 282-289, point to the combined Field 2 March/April setup using:
  - `20230327-p4m/.../B_G_R_RE_NIR_NDVI`
  - `20230412-p4m/.../B_G_R_RE_NIR_NDVI`
- User-provided context: the broader image material covered February to June, but the useful annotation/modeling window was late March to early April because wheat had not yet overgrown black-grass and black-grass had developed enough to differ from wheat.
- Interpretation: the manuscript now separates the broader inspection window from the final experimental subset.

### Sample unit, split, and leakage risk

- `D:/Research/Weed-backup 2026-01-24/weed-utility/src/yolo_prep_dataset.py`, lines 13-17, define `only_use_annotated=True`, seed 42, train split 0.7, and validation split 0.15, with test data as the remainder.
- `D:/Research/Weed-backup 2026-01-24/weed-utility/src/yolo_prep_dataset.py`, lines 201-238, define a reusable split function that sorts and shuffles annotation files, then splits them into train/validation/test.
- `D:/Research/Weed-backup 2026-01-24/weed-utility/src/yolo_prep_dataset.py`, lines 254-270, copies annotation files and corresponding `.npy` image files to train/validation/test directories.
- User-provided context: training, validation, and test samples were assigned from different parts of the field.
- Evidence limitation: I did not find a clean coordinate/zone metadata file in the searched backup paths that independently proves the field-zone split. The manuscript therefore states the split design and adds a within-field limitation rather than claiming full independent field-level generalization.

### Evaluation thresholds

- `D:/Research/Weed-backup 2026-01-24/weed-utility/src/evaluate_yolo.py`, lines 38-58, list the prediction files used for the 5-channel, TGI, ExG, NDVI, WI/NDWI, and TGI 640 configurations at probability export levels such as `prob-0.001`.
- `D:/Research/Weed-backup 2026-01-24/weed-utility/src/evaluate_yolo.py`, lines 145-155, show IoU-based matching in the custom evaluation code.
- Interpretation: the manuscript now defines the threshold in the PR/F1-confidence plots as the detector confidence score sweep, and avoids claiming a single fixed deployment threshold.

### NDVI-assisted annotation

- Manuscript context before this change already stated that RGB and NDVI images were used for annotation.
- User-provided context: NDVI was used as a visual support source together with RGB, not as automatic annotation or label generation.
- Interpretation: the revised manuscript explicitly treats NDVI-assisted annotation as a validity consideration for the NDVI input-channel result.

## Reviewer Response Draft Text

R2-2 / R3-10 / R3-11:

> We agree that the original wording overstated the architectural modification. We revised the manuscript to clarify that the detector is based on YOLOv8 instance segmentation and that the verified adaptation is the input-channel configuration: five aligned spectral bands for the baseline and six channels when one vegetation index is added. The backbone and segmentation head follow the YOLOv8-seg design, and no new detection block is claimed. We also standardized the terminology so the VI cases are described as input-channel configurations rather than separate architectures.

R3-12 / R4-1:

> We added a reproducibility table and a new dataset-construction subsection. The revision states the sample unit, annotated-only filtering, 70/15/15 train/validation/test split with a fixed seed, and the absence of an additional overlapping patch-generation step after aligned image stack generation for the reported experiment. We also added a limitation statement explaining that the split was within the same field and acquisition window, so the results should be interpreted as a controlled within-field comparison rather than a full field-level or seasonal generalization test.

R3-13:

> We clarified that the thresholds in the PR and F1-confidence analyses refer to the detector confidence score assigned to predicted instances. The curves sweep this confidence threshold rather than reporting one selected deployment threshold.

R4-2:

> We agree that using NDVI during annotation and later evaluating NDVI as an input channel is a validity concern. The revised annotation section states that NDVI was used only as visual support, not as an automatic labeling rule, and the limitations section now notes that NDVI-assisted annotation may affect interpretation of the NDVI-channel result.

R4-3:

> We agree that robustness to alignment errors and sensor-domain changes was not evaluated. The revised limitations section now states this explicitly and avoids presenting the results as evidence of robustness across different sensors or noisier capture conditions.

## Claims Not Made

- No claim that a new YOLO architecture block was introduced.
- No claim that YOLOv1, YOLOv2, YOLO-NAS, or other detector-family baselines were newly trained.
- No claim of full geographic, seasonal, or independent-field generalization.
- No claim that leakage risk is fully eliminated.
- No exact runtime or hardware specification beyond what can be verified from available scripts/logs.
