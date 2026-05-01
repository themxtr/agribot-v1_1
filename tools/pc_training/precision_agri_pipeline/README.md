# Precision Agriculture YOLOv8 Pipeline

## Install

```bash
pip install ultralytics numpy scikit-learn matplotlib seaborn sahi
```

For dataset ingestion from Kaggle, install and configure Kaggle CLI credentials.

## 1) Data Ingestion (download + merge + normalize + 80/10/10 split)

```bash
python -m tools.pc_training.precision_agri_pipeline.data_ingestion
```

Output:
- `datasets/unified_rice_weed_yolo/data.yaml`
- YOLO labels/images under `train/val/test`

## 2) Train (P2 head + SimAM+EMA + PIoU/InnerMPDIoU + requested overrides)

```bash
python -m tools.pc_training.precision_agri_pipeline.train_precision_agri \
  --data datasets/unified_rice_weed_yolo/data.yaml \
  --loss innermpdiou
```

## 3) SAHI Inference (640x640, overlap=0.2, NMS IoU=0.75)

```bash
python -m tools.pc_training.precision_agri_pipeline.sahi_inference \
  --model runs/precision_agri/yolov8_p2_simam_ema/weights/best.pt \
  --data datasets/unified_rice_weed_yolo/data.yaml
```

## 4) Evaluation + Bootstrap CI + Publication Plots

```bash
python -m tools.pc_training.precision_agri_pipeline.evaluate_and_plot \
  --model runs/precision_agri/yolov8_p2_simam_ema/weights/best.pt \
  --data datasets/unified_rice_weed_yolo/data.yaml
```

Saved plots (`300 DPI PNG`):
- `confusion_matrix_plasma_dark.png`
- `f1_confidence_glow_curve.png`
- `bootstrap_map50_violin.png`

## 5) End-to-end one command

```bash
python -m tools.pc_training.precision_agri_pipeline.run_pipeline
```

If `best.pt` and `data.yaml` already exist:

```bash
python -m tools.pc_training.precision_agri_pipeline.run_pipeline --skip-ingest --skip-train --data data.yaml --best best.pt
```

