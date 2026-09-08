# IRSTD-AutoLabel

**From infrared images and masks to annotations, error analysis, and publication-ready figures.**

IRSTD-AutoLabel brings automatic annotation and visualization to infrared small target detection (IRSTD), with an interactive web service and a local batch-processing CLI.

[![License](https://img.shields.io/badge/license-Apache--2.0-red.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-%E2%89%A53.10-blue.svg)](https://www.python.org/)
[![Web Demo](https://img.shields.io/badge/Web-Try%20the%20demo-00897B.svg)](http://irstd-autolabel.top/)

**[Try online](http://irstd-autolabel.top/)** · **[Install the CLI](#installation)** · **[English guide](cli/README_EN.md)** · **[中文指南](cli/README.md)**

## Manual vs. automatic annotation

See the workflows in action: manual annotation and automatic annotation with IRSTD-AutoLabel.

<table>
  <tr>
    <th width="50%" align="center">Manual annotation · 手工标注</th>
    <th width="50%" align="center">IRSTD-AutoLabel · 自动化标注</th>
  </tr>
  <tr>
    <td width="50%" align="center" valign="top">
      <video src="https://github.com/user-attachments/assets/8e4a7659-4e12-4e8d-901f-3ccafe18c019" controls preload="metadata" width="100%">
        <a href="https://github.com/user-attachments/assets/8e4a7659-4e12-4e8d-901f-3ccafe18c019">Watch the manual annotation demo</a>
      </video>
    </td>
    <td width="50%" align="center" valign="top">
      <video src="https://github.com/user-attachments/assets/60b1c906-e9d1-4f89-8118-538090b443c7" controls preload="metadata" width="100%">
        <a href="https://github.com/user-attachments/assets/60b1c906-e9d1-4f89-8118-538090b443c7">Watch the automatic annotation demo</a>
      </video>
    </td>
  </tr>
</table>

## Overview

This public repository contains the local, batch-oriented CLI. It reads original infrared images, ground-truth masks, and prediction masks; matches connected components; classifies detections; and exports visualizations and labels in several common formats.

> **Scope:** only the CLI is open source at present. The hosted web interface remains available as a service, but its frontend and backend source code are not included in this repository.

```text
Infrared images + GT masks + prediction masks
                      ↓
        Component matching & A/B/C analysis
                      ↓
     PNG figures · COCO JSON · YOLO TXT · CSV
```

For GT-only annotation, provide original images and GT masks and use `--mode original`.

**On this page:** [Web service](#online-web-service) · [Features](#features) · [Installation](#installation) · [Input layout](#input-layout) · [Usage](#usage) · [Outputs](#output-layout) · [Citation](#citation)

## Online web service

For interactive annotation and browser-based visualization, use the IRSTD-AutoLabel web service:

- **Official domain:** [http://irstd-autolabel.top/](http://irstd-autolabel.top/).
- **Temporary access:** [http://47.94.139.242/](http://47.94.139.242/).

The CLI and web service implement the same main workflow. The CLI is recommended for local data, reproducible experiments, and batch processing. If the hosted service becomes unavailable, we will reassess releasing the web implementation.

## Features

| Capability | What you can do |
| --- | --- |
| **Batch processing** | Automatically detect standard and flat comparison-directory layouts; filter by image stem, method, or prediction source. |
| **Two annotation modes** | Analyze prediction masks against GT, or generate annotations from GT masks alone. |
| **Error analysis** | Identify matched detections, false alarms, and missed targets through component matching. |
| **Figure generation** | Export publication-oriented PNG figures with local zoom panels. |
| **Multiple export formats** | Produce COCO JSON, YOLO TXT, and summary CSV files. |
| **Configurable visualization** | Adjust thresholds, matching strategies, colors, resampling, brightness, and contrast. |

Prediction analysis uses three categories:

| Category | Meaning | Default box color |
| :---: | --- | --- |
| **A** | Matched detection (true positive) | Red |
| **B** | Unmatched prediction (false alarm) | Gold |
| **C** | Unmatched ground-truth target (miss) | Deep sky blue |

## Installation

Python 3.10 or newer is recommended.

```bash
git clone https://github.com/iLearn-Lab/IRSTD-AutoLabel.git
cd IRSTD-AutoLabel

python -m venv .venv
```

Activate the environment:

```bash
# Linux / macOS
source .venv/bin/activate
```

```powershell
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
```

Install the dependencies and verify the CLI:

```bash
python -m pip install -r requirements.txt
python -m cli --help
```

## Input layout

The simplest supported layout is:

```text
data/
├── Original/
│   ├── image_001.png
│   └── image_002.png
├── GT/
│   ├── image_001.png
│   └── image_002.png
├── Method_A/
│   ├── image_001.png
│   └── image_002.png
└── Method_B/
    ├── image_001.png
    └── image_002.png
```

`Original` and `GT` are reserved directory names. Every other sibling directory is treated as a prediction source. Files are paired by the same filename stem. Common image formats are supported: PNG, JPEG, BMP, and TIFF.

Flat numbered layouts used in comparison figures are also supported:

```text
comparison/
├── 0_original_sample_001.png
├── 1_gt_sample_001.png
├── 2_Method_A_sample_001.png
└── 3_Method_B_sample_001.png
```

See the detailed CLI guide in [English](cli/README_EN.md) or [简体中文](cli/README.md) for all supported layouts and naming rules.

## Usage

### Batch annotation

Process all prediction sources and export PNG, COCO, YOLO, and CSV results:

```bash
python -m cli --input /path/to/data --format all
```

### Select a source or method

Process a single source or method:

```bash
python -m cli --input /path/to/data --source Method_A
python -m cli --input /path/to/data --model Method_A
```

### GT-only annotation

Generate annotations from original images and GT masks without prediction masks:

```bash
python -m cli --input /path/to/data --mode original --format png,csv
```

### Customize matching and visualization

Tune the matching threshold, strategy, and category colors:

```bash
python -m cli --input /path/to/data \
  --threshold 5 \
  --strategy distance \
  --color-a "#FF0000" \
  --color-b "#FFD700" \
  --color-c "#00BFFF"
```

Use `--output /path/to/results` to keep generated files outside the input directory. Run `python -m cli --help` for the complete option list.

## Output layout

With `--format all`, the output directory contains:

```text
output_cli/
├── coco/
│   └── Method_A_image_001.json
├── yolo/
│   └── Method_A_image_001.txt
├── visualizations/
│   └── Method_A_image_001.png
└── summary.csv
```

COCO and YOLO exports contain positive target boxes. In prediction mode these are the A and C categories; false alarms (B) are excluded from positive labels. `summary.csv` retains the A/B/C counts for each image and method.

## Repository scope

```text
IRSTD-AutoLabel/
├── assets/                 # Manual and automatic annotation demo videos
│   ├── humanlabel.mp4
│   └── autolable.mp4
├── cli/                    # Open-source command-line implementation
│   ├── README_EN.md         # Detailed English CLI guide
│   └── README.md            # Detailed Chinese CLI guide
├── CITATION.cff.template    # Software citation template
├── README.md
├── requirements.txt
└── LICENSE
```

No web application source, private data, model checkpoints, generated results, or internal development documents are distributed here.

## Citation

Software citation metadata will be added after the contributor list and archival DOI are finalized. A `CITATION.cff.template` is included for maintainers; do not rename it until all `TODO` values have been replaced.

If you use IRSTD-AutoLabel, please cite the associated papers:

- [DGNet](https://github.com/iLearn-Lab/MM26-DGNet)
- [ADGNet](https://github.com/iLearn-Lab/MM26-ADGNet)
- [HDNet](https://github.com/iLearn-Lab/TGRS25-HDNet)

### BibTeX citations

```bibtex
@inproceedings{yu2026dgnet,
  title     = {DGNet: Dual-knowledge Guided Network for Infrared Small Target Detection},
  author    = {Yu, Chenglong and Xu, Mingzhu and Wang, Jing and Wang, Tongtong and Miao, Pingping and Nie, Liqiang},
  booktitle = {Proceedings of the ACM International Conference on Multimedia},
  year      = {2026},
}

@inproceedings{wang2026adgnet,
  title     = {ADGNet: Asymmetric Dual-text Guided Network for Infrared Small Target Detection},
  author    = {Wang, Tongtong and Xu, Mingzhu and Yu, Chenglong and Wang, Jing and Lin, Xiaohui and Guan, Weili},
  booktitle = {Proceedings of the ACM International Conference on Multimedia},
  year      = {2026},
}

@article{11017756,
  author  = {Xu, Mingzhu and Yu, Chenglong and Li, Zexuan and Tang, Haoyu and Hu, Yupeng and Nie, Liqiang},
  journal = {IEEE Transactions on Geoscience and Remote Sensing},
  title   = {HDNet: A Hybrid Domain Network With Multiscale High-Frequency Information Enhancement for Infrared Small-Target Detection},
  year    = {2025},
  volume  = {63},
  pages   = {1--15},
  doi     = {10.1109/TGRS.2025.3574962},
}
```

For future papers that use the tool, we recommend mentioning both the repository and the hosted web service in the main text or implementation section, rather than only in a footnote. Once an archival DOI is available, cite the software DOI as well.

## License

IRSTD-AutoLabel is released under the [Apache License 2.0](LICENSE).

## Contributions and issues

Bug reports and focused pull requests for the CLI are welcome through GitHub Issues. When reporting a problem, include the command, directory layout, Python/Pillow versions, and a minimal reproducible example. Please do not upload private datasets or unpublished model outputs.

If you have any questions, please contact [yucl@mail.sdu.edu.cn](mailto:yucl@mail.sdu.edu.cn).
