"""
Batch labeling CLI tool for IRSTD.

Usage:
    python -m cli.batch_label_cli --input figures/SOTA_duibi
    python -m cli.batch_label_cli --input figures --source Method_A_Pred
    python -m cli.batch_label_cli --input figures/SOTA_duibi --mode original

Prerequisites:
    pip install Pillow
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from PIL import Image

from .core import analyze_original, analyze_prediction, load_image
from .detector import build_task_list, detect_structure
from .exporter import export_summary_csv, export_task_result, print_summary
from .visualizer import DEFAULT_COLORS, render_task

RESAMPLE_METHODS = {
    "nearest": Image.Resampling.NEAREST,
    "bilinear": Image.Resampling.BILINEAR,
    "bicubic": Image.Resampling.BICUBIC,
    "lanczos": Image.Resampling.LANCZOS,
    "box": Image.Resampling.BOX,
    "hamming": Image.Resampling.HAMMING,
}


def parse_color(value: str) -> tuple[int, int, int]:
    """Parse #RRGGBB or R,G,B into an RGB tuple."""
    text = value.strip()

    if text.startswith("#"):
        hex_value = text[1:]
        if len(hex_value) != 6:
            raise argparse.ArgumentTypeError("Expected color format #RRGGBB.")
        try:
            return (
                int(hex_value[0:2], 16),
                int(hex_value[2:4], 16),
                int(hex_value[4:6], 16),
            )
        except ValueError as exc:
            raise argparse.ArgumentTypeError("Expected color format #RRGGBB.") from exc

    parts = [part.strip() for part in text.split(",")]
    if len(parts) != 3:
        raise argparse.ArgumentTypeError("Expected color format #RRGGBB or R,G,B.")

    try:
        channels = tuple(int(part) for part in parts)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("RGB channels must be integers.") from exc

    if any(channel < 0 or channel > 255 for channel in channels):
        raise argparse.ArgumentTypeError("RGB channels must be between 0 and 255.")

    return channels


def build_color_config(args: argparse.Namespace) -> dict[str, tuple[int, int, int]]:
    """Return color config merged with CLI overrides."""
    return {
        "A": args.color_a or DEFAULT_COLORS["A"],
        "B": args.color_b or DEFAULT_COLORS["B"],
        "C": args.color_c or DEFAULT_COLORS["C"],
        "GT": args.color_gt or DEFAULT_COLORS["GT"],
    }


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Batch labeling tool for IRSTD",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Prediction mode (default)
  python -m cli.batch_label_cli --input figures/SOTA_duibi

  # Original mode
  python -m cli.batch_label_cli --input figures/SOTA_duibi --mode original

  # Specify prediction source
  python -m cli.batch_label_cli --input figures --source Method_A_Pred

  # Filter by image stem
  python -m cli.batch_label_cli --input figures/SOTA_duibi --stem XDU104

  # Custom threshold and output
  python -m cli.batch_label_cli --input figures/SOTA_duibi --threshold 5 --output results/
        """,
    )

    parser.add_argument(
        "--input",
        type=str,
        required=True,
        help="Input directory path",
    )
    parser.add_argument(
        "--mode",
        choices=["prediction", "original"],
        default="prediction",
        help="Labeling mode: prediction (A/B/C) or original (GT only)",
    )
    parser.add_argument(
        "--source",
        type=str,
        default=None,
        help="Prediction source name (for standard structure)",
    )
    parser.add_argument(
        "--stem",
        type=str,
        default=None,
        help="Filter by image stem (e.g., XDU104, Misc_29)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Filter by model name (e.g., Method_A, Method_B)",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=3.0,
        help="Center-distance threshold in pixels (default: 3.0)",
    )
    parser.add_argument(
        "--strategy",
        choices=["confidence", "distance"],
        default="confidence",
        help="Matching strategy: confidence or distance priority",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output directory (default: <input>/output_cli)",
    )
    parser.add_argument(
        "--format",
        type=str,
        default="all",
        help="Export formats: coco, yolo, png, csv, all (comma-separated)",
    )
    parser.add_argument(
        "--box-size",
        type=float,
        default=30.0,
        help="Default box size for standardization (default: 30)",
    )
    parser.add_argument(
        "--stroke-width",
        type=int,
        default=1,
        help="Small box stroke width in pixels (default: 1, zoom border always 8px)",
    )
    parser.add_argument(
        "--panel-padding",
        type=int,
        default=2,
        help="Padding between target edge and zoom panel edge (default: 2)",
    )
    parser.add_argument(
        "--adaptive-padding",
        type=int,
        default=4,
        help="Adaptive box padding in pixels (default: 4)",
    )
    parser.add_argument(
        "--brightness",
        type=float,
        default=1.0,
        help="Brightness adjustment factor (default: 1.0)",
    )
    parser.add_argument(
        "--contrast",
        type=float,
        default=1.0,
        help="Contrast adjustment factor (default: 1.0)",
    )
    parser.add_argument(
        "--mask-resample",
        choices=sorted(RESAMPLE_METHODS),
        default="nearest",
        help="Interpolation for resizing GT/pred masks before component extraction (default: nearest)",
    )
    parser.add_argument(
        "--base-resample",
        choices=sorted(RESAMPLE_METHODS),
        default="lanczos",
        help="Interpolation for resizing the full base image to export resolution (default: lanczos)",
    )
    parser.add_argument(
        "--zoom-resample",
        choices=sorted(RESAMPLE_METHODS),
        default="nearest",
        help="Interpolation for zooming source pixels before cropping zoom panels (default: nearest)",
    )
    parser.add_argument(
        "--panel-resample",
        choices=sorted(RESAMPLE_METHODS),
        default="nearest",
        help="Interpolation for resizing zoom crops/panels to their final size (default: nearest)",
    )
    parser.add_argument(
        "--color-a",
        type=parse_color,
        default=None,
        metavar="COLOR",
        help="A / true-positive box color as #RRGGBB or R,G,B (default: #FF0000)",
    )
    parser.add_argument(
        "--color-b",
        type=parse_color,
        default=None,
        metavar="COLOR",
        help="B / false-alarm box color as #RRGGBB or R,G,B (default: #FFD700)",
    )
    parser.add_argument(
        "--color-c",
        type=parse_color,
        default=None,
        metavar="COLOR",
        help="C / miss box color as #RRGGBB or R,G,B (default: #00BFFF)",
    )
    parser.add_argument(
        "--color-gt",
        type=parse_color,
        default=None,
        metavar="COLOR",
        help="GT box color in original mode as #RRGGBB or R,G,B (default: #FF0000)",
    )
    parser.add_argument(
        "--no-viz",
        action="store_true",
        help="Skip visualization export",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output",
    )

    return parser.parse_args()


def get_export_formats(format_str: str) -> list[str]:
    """Parse format string into list of formats."""
    if format_str.lower() == "all":
        return ["coco", "yolo", "png", "csv"]

    formats = []
    for f in format_str.split(","):
        f = f.strip().lower()
        if f in ("coco", "yolo", "png", "csv"):
            formats.append(f)

    return formats if formats else ["coco", "yolo", "png", "csv"]


def main() -> int:
    """Main entry point."""
    args = parse_args()

    # Resolve paths
    input_dir = Path(args.input).resolve()
    if not input_dir.exists():
        print(f"[ERROR] Input directory not found: {input_dir}")
        return 1

    # Determine output directory
    if args.output:
        output_dir = Path(args.output).resolve()
    else:
        output_dir = input_dir / "output_cli"

    # Parse formats
    formats = get_export_formats(args.format)
    mask_resample = RESAMPLE_METHODS[args.mask_resample]
    base_resample = RESAMPLE_METHODS[args.base_resample]
    zoom_resample = RESAMPLE_METHODS[args.zoom_resample]
    panel_resample = RESAMPLE_METHODS[args.panel_resample]
    colors = build_color_config(args)

    # Detect directory structure
    print(f"\n[1/4] Detecting directory structure: {input_dir}")
    try:
        structure = detect_structure(input_dir)
    except ValueError as e:
        print(f"[ERROR] {e}")
        return 1

    print(f"  Structure type: {structure['type']}")
    print(f"  Originals: {len(structure['originals'])}")
    print(f"  GT: {len(structure['gt'])}")
    print(f"  Prediction sources: {structure['sources']}")

    # Build task list
    print(f"\n[2/4] Building task list (mode: {args.mode})")
    try:
        tasks = build_task_list(
            structure,
            mode=args.mode,
            source=args.source,
            stem_filter=args.stem,
            model_filter=args.model,
        )
    except ValueError as e:
        print(f"[ERROR] {e}")
        return 1

    if not tasks:
        print("[WARN] No tasks found matching filters.")
        print(f"  Available sources: {structure['sources']}")
        print(f"  Available stems: {sorted(structure['originals'].keys())[:10]}...")
        return 1

    print(f"  Found {len(tasks)} tasks")

    if args.verbose:
        for t in tasks[:5]:
            print(f"    {t['stem']} | {t['model']} | {t['mode']}")
        if len(tasks) > 5:
            print(f"    ... and {len(tasks) - 5} more")

    # Process tasks
    print(f"\n[3/4] Processing tasks (threshold: {args.threshold}, strategy: {args.strategy})")
    print(f"  Output directory: {output_dir}")
    print(f"  Export formats: {', '.join(formats)}")
    print()

    results = []
    start_time = time.time()

    for i, task in enumerate(tasks, 1):
        stem = task["stem"]
        model = task["model"]
        mode = task["mode"]

        progress = f"[{i}/{len(tasks)}]"
        print(f"{progress} {stem} | {model} | {mode} | Analyzing...", end="", flush=True)

        try:
            # Load images
            gt_image = load_image(task["gt"])

            # Analyze based on mode
            if mode == "original":
                analysis_result = analyze_original(
                    gt_image,
                    adaptive_padding=args.adaptive_padding,
                    mask_resample=mask_resample,
                )
            else:
                pred_image = load_image(task["prediction"])
                analysis_result = analyze_prediction(
                    gt_image,
                    pred_image,
                    threshold=args.threshold,
                    strategy=args.strategy,
                    adaptive_padding=args.adaptive_padding,
                    mask_resample=mask_resample,
                )

            # Export results
            result = export_task_result(task, analysis_result, output_dir, formats)
            results.append(result)

            # Render visualization
            if "png" in formats and not args.no_viz:
                viz_image = render_task(
                    task,
                    analysis_result,
                    stroke_width=args.stroke_width,
                    brightness=args.brightness,
                    contrast=args.contrast,
                    panel_padding=args.panel_padding,
                    base_resample=base_resample,
                    zoom_resample=zoom_resample,
                    panel_resample=panel_resample,
                    colors=colors,
                )

                viz_dir = output_dir / "visualizations"
                viz_dir.mkdir(parents=True, exist_ok=True)
                viz_path = viz_dir / f"{model}_{stem}.png"
                viz_image.save(viz_path, "PNG")

            # Print result
            if mode == "prediction":
                a_cnt = result.get("A", 0)
                b_cnt = result.get("B", 0)
                c_cnt = result.get("C", 0)
                print(f" A={a_cnt} B={b_cnt} C={c_cnt} | Done")
            else:
                gt_cnt = result.get("gt_components", 0)
                print(f" GT={gt_cnt} | Done")

        except Exception as e:
            print(f" FAILED: {e}")
            if args.verbose:
                import traceback
                traceback.print_exc()
            continue

    elapsed = time.time() - start_time

    # Write summary CSV
    if "csv" in formats and results:
        print(f"\n[4/4] Writing summary")
        csv_path = output_dir / "summary.csv"
        export_summary_csv(results, csv_path)
        print(f"  Summary saved to: {csv_path}")
    else:
        print(f"\n[4/4] Complete")

    # Print summary
    print_summary(results)

    print(f"\nTotal time: {elapsed:.1f}s")
    print(f"Results saved to: {output_dir}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
