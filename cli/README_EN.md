# IRSTD-AutoLabel CLI

**English** | [简体中文](README.md)

A command-line batch annotation tool for automatic evaluation, visualization, and label export in infrared small target detection (IRSTD). The CLI requires no browser. It reads original images, ground-truth masks, and prediction masks directly from local directories, then generates publication-ready figures, COCO annotations, YOLO labels, and summary CSV files in batches.

> Only the command-line implementation is currently open source. The interactive web version is provided as an online service, while its frontend and backend source code are not included in this repository. See [Online web service](../README.md#online-web-service) in the top-level README for access.

## Features

- Automatically detects three directory layouts: `standard`, `sota_flat`, and `numbered_flat`.
- Supports two processing modes:
  - `prediction`: evaluates prediction masks and produces A/B/C results.
  - `original`: annotates original images using GT masks only.
- Exports PNG, COCO JSON, YOLO TXT, and CSV files.
- Filters tasks by `stem`, `model`, or `source`.
- Provides CLI controls for interpolation, box colors, brightness, contrast, border width, and zoom-panel padding.
- Automatically creates local zoom panels for A/B targets; C targets are marked only on the main image.

## Installation

```bash
pip install Pillow
```

Run the following command from the repository root:

```bash
python -m cli.batch_label_cli --help
```

## Input directories and naming conventions

Before running the CLI, organize your images using any of the layouts below. The program detects the directory type automatically and pairs original images, GT masks, and prediction masks by filename.

Supported image extensions:

```text
.png, .jpg, .jpeg, .bmp, .tif, .tiff
```

### Layout 1: Standard

This layout is suitable for conventional datasets. Store original images in `Original`, ground-truth masks in `GT`, and each set of prediction masks in another sibling directory.

```text
figures/
├── Original/
│   ├── XDU104.png
│   └── Misc_29.png
├── GT/
│   ├── XDU104.png
│   └── Misc_29.png
├── Method_A/
│   ├── XDU104.png
│   └── Misc_29.png
└── Method_B/
    ├── XDU104.png
    └── Misc_29.png
```

Rules:

- `Original/` and `GT/` are reserved directory names.
- Every other sibling directory is treated as a prediction source. Use `--source Method_A` to select one.
- Files are paired by the same stem. For example, `XDU104.png` is matched across `Original/XDU104.png`, `GT/XDU104.png`, and `Method_A/XDU104.png`.
- Nested directories are supported. The CLI first matches by relative path and falls back to files with the same name when necessary.

### Layout 2: SOTA Flat

This flat layout is suitable for paper comparison figures. Store all images in one directory and use numeric prefixes to distinguish original images, GT masks, and predictions from different methods.

```text
figures/SOTA_comparison/
├── 0_original_000041.png
├── 1_gt_000041.png
├── 2_Method_A_000041.png
├── 3_Method_B_000041.png
└── 4_Method_C_000041_Pred.png
```

Rules:

- `0_...`: original image.
- `1_...`: GT mask.
- `2_...` and larger numeric prefixes: prediction masks.
- Prefixes such as `original_`, `gt_`, and `ori_` are removed automatically when matching stems.
- Prediction files normally follow `number_method_stem.png`, such as `2_Method_A_000041.png`.
- The `_Pred` suffix is supported, such as `4_Method_C_000041_Pred.png`.

### Layout 3: Numbered Flat

This flat layout is suitable for ablation-study directories. All images are stored together, while the original and GT filenames usually omit `original_` and `gt_` labels.

```text
figures/ablation/gcc/
├── 0_Misc_92.png
├── 1_Misc_92.png
├── 2_Method_A_Misc_92.png
└── 3_sigma2_Misc_92.png
```

Rules:

- `0_stem.png`: original image.
- `1_stem.png`: GT mask.
- `2_method_stem.png` and larger numeric prefixes: prediction masks.
- Stems may contain underscores, such as `Misc_92`.

### Minimum required files

Each task requires at least:

```text
1 original image
1 GT mask
1 prediction mask (in prediction mode)
```

With `--mode original`, only the original image and GT mask are required; prediction masks are not read.

## Quick start

```bash
# Prediction mode is the default; process the entire directory
python -m cli.batch_label_cli --input figures/SOTA_comparison

# Original mode: annotate the original image using the GT mask only
python -m cli.batch_label_cli --input figures/SOTA_comparison --mode original

# Process one image and one method only
python -m cli.batch_label_cli --input figures/SOTA_comparison --stem 000041 --model Method_A
```

## Arguments

### Basic arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `--input` | Required | Input directory path |
| `--mode` | `prediction` | Processing mode: `prediction` or `original` |
| `--output` | `<input>/output_cli` | Output directory |
| `--format` | `all` | Export formats: `coco`, `yolo`, `png`, `csv`, or `all`; accepts comma-separated values |

### Filtering arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `--source` | None | Prediction source, mainly for the `standard` layout |
| `--stem` | None | Image-stem filter, such as `XDU104`, `000041`, or `Misc_29` |
| `--model` | None | Method-name filter, such as `Method_A` or `Method_B` |

### Matching and box-generation arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `--threshold` | `3.0` | Center-distance matching threshold in pixels |
| `--strategy` | `confidence` | Conflict-resolution strategy: `confidence` or `distance` |
| `--adaptive-padding` | `4` | Extra padding for adaptive boxes, in pixels |
| `--box-size` | `30.0` | Reserved argument; core box size is currently controlled by `--adaptive-padding` |

### Visualization arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `--stroke-width` | `1` | Width of small boxes on the main image |
| `--panel-padding` | `2` | Distance between the target boundary and zoom-panel boundary |
| `--brightness` | `1.0` | Brightness factor |
| `--contrast` | `1.0` | Contrast factor |
| `--no-viz` | `False` | Skip PNG visualization and export data files only |
| `--verbose` / `-v` | `False` | Print detailed error traces |

## Interpolation controls

Supported interpolation methods:

```text
nearest, bilinear, bicubic, lanczos, box, hamming
```

| Argument | Default | Scope |
|----------|---------|-------|
| `--mask-resample` | `nearest` | Resize GT/prediction masks before connected-component extraction |
| `--base-resample` | `lanczos` | Resize the full base image to the export resolution |
| `--zoom-resample` | `nearest` | Upscale source pixels before producing local zoom panels |
| `--panel-resample` | `nearest` | Resize local crops or zoom panels to their final size |

The defaults preserve the original behavior:

- Masks: `nearest`
- Local zoom: `nearest`
- Zoom panels: `nearest`
- Exported base image: `lanczos`

Example:

```bash
python -m cli.batch_label_cli --input figures/SOTA_comparison \
  --mask-resample nearest \
  --base-resample lanczos \
  --zoom-resample nearest \
  --panel-resample nearest
```

To preserve a pixelated appearance in every resizing stage:

```bash
python -m cli.batch_label_cli --input figures/SOTA_comparison \
  --base-resample nearest \
  --zoom-resample nearest \
  --panel-resample nearest
```

## Color controls

Colors accept either format:

```text
#RRGGBB
R,G,B
```

| Argument | Default | Description |
|----------|---------|-------------|
| `--color-a` | `#FF0000` | A / true-positive box color |
| `--color-b` | `#FFD700` | B / false-alarm box color |
| `--color-c` | `#00BFFF` | C / miss box color |
| `--color-gt` | `#FF0000` | GT box color in `original` mode |

Mode behavior:

- `--mode prediction` uses `--color-a`, `--color-b`, and `--color-c`.
- `--mode original` uses only `--color-gt`; the A/B/C color arguments are ignored.

Example:

```bash
python -m cli.batch_label_cli --input figures/SOTA_comparison --stem 000041 --model Method_A \
  --color-a "#00FF00" \
  --color-b "255,128,0" \
  --color-c "#3366FF" \
  --color-gt "#FF00FF"
```

Change the color in original mode:

```bash
python -m cli.batch_label_cli --input figures/SOTA_comparison --mode original --stem 000041 \
  --format png,csv \
  --color-gt "#00FFFF"
```

## Common examples

### Matching adjustments

```bash
# Increase the center-distance matching threshold
python -m cli.batch_label_cli --input figures/SOTA_comparison --threshold 5

# Prioritize distance instead of confidence
python -m cli.batch_label_cli --input figures/SOTA_comparison --strategy distance
```

### Visualization adjustments

```bash
# Increase brightness and contrast
python -m cli.batch_label_cli --input figures/SOTA_comparison --brightness 1.2 --contrast 1.15

# Increase the small-box stroke width and zoom-panel padding
python -m cli.batch_label_cli --input figures/SOTA_comparison --stroke-width 2 --panel-padding 4

# Change adaptive-box padding
python -m cli.batch_label_cli --input figures/SOTA_comparison --adaptive-padding 8
```

### Export controls

```bash
# Export PNG and CSV only
python -m cli.batch_label_cli --input figures/SOTA_comparison --format png,csv

# Export COCO, YOLO, and CSV without PNG visualizations
python -m cli.batch_label_cli --input figures/SOTA_comparison --no-viz --format coco,yolo,csv

# Specify an output directory
python -m cli.batch_label_cli --input figures/SOTA_comparison --output results/
```

### Complete example

```bash
python -m cli.batch_label_cli --input figures/SOTA_comparison --stem 000041 --model Method_A \
  --format png,csv \
  --threshold 3 \
  --strategy confidence \
  --adaptive-padding 4 \
  --stroke-width 1 \
  --brightness 1.1 \
  --contrast 1.1 \
  --mask-resample nearest \
  --base-resample lanczos \
  --zoom-resample nearest \
  --panel-resample nearest \
  --color-a "#FF0000" \
  --color-b "#FFD700" \
  --color-c "#00BFFF"
```

In Windows PowerShell, use backticks for line continuation:

```powershell
python -m cli.batch_label_cli --input figures\SOTA_comparison --stem 000041 --model Method_A `
  --format png,csv `
  --mask-resample nearest `
  --base-resample lanczos `
  --zoom-resample nearest `
  --panel-resample nearest `
  --color-a "#FF0000" `
  --color-b "255,215,0" `
  --color-c "#00BFFF"
```

## Output layout

```text
<input>/output_cli/
├── summary.csv
├── coco/
│   ├── Method_A_XDU104.json
│   └── ...
├── yolo/
│   ├── Method_A_XDU104.txt
│   └── ...
└── visualizations/
    ├── Method_A_XDU104.png
    └── ...
```

## Result categories

Prediction mode:

- `A`: true positive; the prediction is matched to a GT target; red by default.
- `B`: false alarm; the prediction is not matched to any GT target; yellow by default.
- `C`: miss; the GT target is not matched to any prediction; blue by default.
- A/B targets receive local zoom panels; C targets are shown only as small boxes on the main image.

Original mode:

- Generates annotation boxes on the original image from GT targets; red by default.
- Box color is controlled by `--color-gt`; `--color-a`, `--color-b`, and `--color-c` affect prediction mode only.
- A local zoom panel is generated for every GT target.

## Fixed constants

The following values remain code-level constants and currently have no CLI arguments:

| Constant | Current value | Description |
|----------|---------------|-------------|
| `ZOOM_PANEL_SIZE` | `188` | Base size of each local zoom panel |
| `DEFAULT_ZOOM_BORDER_WIDTH` | `8` | Border width of local zoom panels |
| `EXPORT_LONGEST_SIDE` | `960` | Longest side of an exported image |
| `ZOOM_GROUP_DISTANCE` | `20` | Distance threshold for merging nearby targets into one zoom panel |

## Verification commands

```bash
python -m cli.batch_label_cli --help
python -m cli.batch_label_cli --input figures/SOTA_comparison --stem 000041 --model Method_A --format png,csv
```
