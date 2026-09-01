# IRSTD-AutoLabel

Automatic annotation, error analysis, and publication-ready visualization for infrared small target detection (IRSTD).

[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-%E2%89%A53.10-blue.svg)](https://www.python.org/)

This public repository contains the local, batch-oriented CLI. It reads original infrared images, ground-truth masks, and prediction masks; matches connected components; classifies detections; and exports visualizations and labels in several common formats.

> **Scope:** only the CLI is open source at present. The hosted web interface remains available as a service, but its frontend and backend source code are not included in this repository.

## Online web service

For interactive annotation and browser-based visualization, use the IRSTD-AutoLabel web service:

- **Official domain:** [http://irstd-autolabel.top/](http://irstd-autolabel.top/) — currently pending domain approval.
- **Temporary access:** [http://47.94.139.242/](http://47.94.139.242/) — available while the official domain is under review.

The CLI and web service implement the same main workflow. The CLI is recommended for local data, reproducible experiments, and batch processing. If the hosted service becomes unavailable, we will reassess releasing the web implementation.

## Features

- Automatically detects standard and flat comparison-directory layouts.
- Supports prediction analysis and GT-only annotation modes.
- Classifies prediction results as:
  - **A**: matched detection (true positive)
  - **B**: unmatched prediction (false alarm)
  - **C**: unmatched ground-truth target (miss)
- Produces publication-oriented PNG visualizations with local zoom panels.
- Exports COCO JSON, YOLO TXT, and summary CSV files.
- Supports filtering by image stem, method, and prediction source.
- Provides configurable thresholds, matching strategies, colors, resampling, brightness, and contrast.

## Installation

Python 3.10 or newer is recommended.

```bash
git clone https://github.com/iLearn-Lab/IRSTD-AutoLabel.git
cd IRSTD-AutoLabel

python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Check the command:

```bash
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

Process all prediction sources:

```bash
python -m cli --input /path/to/data
```

Process a single source or method:

```bash
python -m cli --input /path/to/data --source Method_A
python -m cli --input /path/to/data --model Method_A
```

Generate GT-only annotations:

```bash
python -m cli --input /path/to/data --mode original --format png,csv
```

Tune matching and visualization:

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
├── cli/                    # Open-source command-line implementation
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
