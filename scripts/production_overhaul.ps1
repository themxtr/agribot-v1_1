#requires -Version 5.1
<#
.SYNOPSIS
End-to-end production pipeline for Agribot precision agriculture detection.

.DESCRIPTION
Runs ingestion, training, SAHI inference, evaluation, random QA export, and git stage/commit/push.
Designed to execute top-to-bottom with no manual edits.
#>

$ErrorActionPreference = 'Stop'

param(
  [string]$Workspace = 'D:\agribot',
  [string]$ModelPath = 'C:\Users\FRIDAY\runs\detect\runs\precision_agri\yolov8_p2_simam_ema-4\weights\best.pt',
  [string]$DataYaml = 'D:\agribot\datasets\unified_rice_weed_yolo\data.yaml',
  [string]$RemoteUrl = 'https://github.com/themxtr/agribot-v1_1.git'
)

Set-Location $Workspace

Write-Host '[1/8] Build unified dataset (local + partial online)'
python -m tools.pc_training.precision_agri_pipeline.run_pipeline `
  --skip-train --skip-sahi --skip-eval `
  --local-dataset-roots cropweed_dataset cropweed_yolo_dataset `
  --allow-partial-downloads --online-sample-ratio 0.25 --online-max-samples 300

Write-Host '[2/8] Train SAHI-ready YOLO pipeline'
python -m tools.pc_training.precision_agri_pipeline.run_pipeline `
  --skip-ingest --skip-sahi --skip-eval `
  --data $DataYaml --device cpu --epochs 50 --imgsz 512 --batch 1 --workers 0 --cpu-safe

Write-Host '[3/8] Evaluate and generate publication plots'
python -m tools.pc_training.precision_agri_pipeline.evaluate_and_plot `
  --model $ModelPath --data $DataYaml --imgsz 512 --batch 1 --device cpu --output-dir runs/precision_agri/eval

Write-Host '[4/8] Sync results artifacts'
New-Item -ItemType Directory -Force results | Out-Null
Copy-Item -Force runs\precision_agri\eval\*.png results\
Copy-Item -Force runs\precision_agri\eval\metrics_summary.json results\metrics_summary.json

Write-Host '[5/8] Run 50-image random QA export'
if (Test-Path runs\random_weed_checks) { Remove-Item -Recurse -Force runs\random_weed_checks }
python -m tools.pc_training.test_random_weed_samples `
  --model $ModelPath --dataset $DataYaml --split train --num-samples 50 --imgsz 512 --device cpu --save-annotated --output-dir runs/random_weed_checks

Write-Host '[6/8] Lint by compile'
python -m compileall src tools

Write-Host '[7/8] Git stage + conventional commit'
if (-not (Test-Path .git)) {
  git init
  git branch -M main
}

git add -A

$commitMessage = @"
feat(perception): integrate SAHI-wrapped YOLOv8 runtime into ROS lifecycle camera pipeline

refactor(training): consolidate precision-agri pipeline and remove deprecated experiment scripts

docs(readme): rewrite project documentation with metrics tables, architecture diagram, inline plots, and references

fix(eval): harden path mapping and numpy AUC compatibility for reproducible plot generation
"@

$commitMessage | Set-Content .git\COMMIT_EDITMSG
git commit -F .git\COMMIT_EDITMSG

Write-Host '[8/8] Push to GitHub main'
if (-not (git remote | Select-String -SimpleMatch origin)) {
  git remote add origin $RemoteUrl
}

git push -u origin main

