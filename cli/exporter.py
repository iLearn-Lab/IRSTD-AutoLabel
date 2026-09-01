"""Export functionality for batch labeling results."""
from __future__ import annotations

import csv
import json
from pathlib import Path


def export_coco_json(
    boxes: list[dict],
    image_size: tuple[int, int],
    image_filename: str,
    output_path: Path,
) -> None:
    """
    Export boxes in COCO JSON format.

    Args:
        boxes: List of box dicts with x, y, width, height
        image_size: (width, height) tuple
        image_filename: Source image filename
        output_path: Output file path
    """
    width, height = image_size

    coco = {
        "images": [
            {
                "id": 1,
                "file_name": image_filename,
                "width": width,
                "height": height,
            }
        ],
        "annotations": [],
        "categories": [
            {"id": 1, "name": "target", "supercategory": "object"}
        ],
    }

    for i, box in enumerate(boxes, 1):
        coco["annotations"].append(
            {
                "id": i,
                "image_id": 1,
                "category_id": 1,
                "bbox": [
                    round(box["x"], 2),
                    round(box["y"], 2),
                    round(box["width"], 2),
                    round(box["height"], 2),
                ],
                "area": round(box["width"] * box["height"], 2),
                "iscrowd": 0,
            }
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(coco, f, indent=2)


def export_yolo_txt(
    boxes: list[dict],
    image_size: tuple[int, int],
    output_path: Path,
) -> None:
    """
    Export boxes in YOLO TXT format.

    Args:
        boxes: List of box dicts with x, y, width, height
        image_size: (width, height) tuple
        output_path: Output file path
    """
    width, height = image_size

    lines = []
    for box in boxes:
        # Convert to YOLO format: class x_center y_center width height (normalized)
        x_center = (box["x"] + box["width"] / 2) / width
        y_center = (box["y"] + box["height"] / 2) / height
        w = box["width"] / width
        h = box["height"] / height

        lines.append(f"0 {x_center:.6f} {y_center:.6f} {w:.6f} {h:.6f}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def export_summary_csv(results: list[dict], output_path: Path) -> None:
    """
    Export summary CSV with all task results.

    Args:
        results: List of result dicts
        output_path: Output file path
    """
    if not results:
        return

    fieldnames = [
        "stem",
        "model",
        "mode",
        "A",
        "B",
        "C",
        "gt_components",
        "pred_components",
    ]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for row in results:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def export_task_result(
    task: dict,
    analysis_result: dict,
    output_dir: Path,
    formats: list[str],
) -> dict:
    """
    Export results for a single task.

    Args:
        task: Task dict
        analysis_result: Analysis result from core module
        output_dir: Output directory
        formats: List of formats to export ("coco", "yolo", "png")

    Returns:
        Summary dict for CSV export
    """
    stem = task["stem"]
    model = task["model"]
    mode = task.get("mode", "prediction")

    # Determine which boxes to export
    if mode == "prediction":
        classified = analysis_result.get("classified_boxes", {})
        # Positive samples = A + C (exclude B)
        positive_boxes = classified.get("A", []) + classified.get("C", [])
        image_size = analysis_result.get("image_size", (0, 0))

        counts = {
            "A": len(classified.get("A", [])),
            "B": len(classified.get("B", [])),
            "C": len(classified.get("C", [])),
        }
        gt_count = len(analysis_result.get("gt_boxes", []))
        pred_count = len(analysis_result.get("pred_boxes", []))
    else:
        # Original mode: export GT boxes
        positive_boxes = analysis_result.get("gt_boxes", [])
        image_size = analysis_result.get("image_size", (0, 0))

        counts = {"A": 0, "B": 0, "C": len(positive_boxes)}
        gt_count = len(positive_boxes)
        pred_count = 0

    # Export in requested formats
    base_name = f"{model}_{stem}"

    if "coco" in formats:
        coco_path = output_dir / "coco" / f"{base_name}.json"
        export_coco_json(
            positive_boxes,
            image_size,
            f"{stem}.png",
            coco_path,
        )

    if "yolo" in formats:
        yolo_path = output_dir / "yolo" / f"{base_name}.txt"
        export_yolo_txt(positive_boxes, image_size, yolo_path)

    return {
        "stem": stem,
        "model": model,
        "mode": mode,
        "A": counts["A"],
        "B": counts["B"],
        "C": counts["C"],
        "gt_components": gt_count,
        "pred_components": pred_count,
    }


def print_summary(results: list[dict]) -> None:
    """Print per-model summary statistics."""
    if not results:
        print("No results to summarize.")
        return

    print("\n=== Per-Model Summary ===")
    print(f"{'Model':<20} {'Mode':<10} {'Images':>8} {'A':>8} {'B':>8} {'C':>8}")
    print("-" * 62)

    model_stats: dict[str, dict] = {}
    for r in results:
        key = f"{r['model']} ({r['mode']})"
        if key not in model_stats:
            model_stats[key] = {"count": 0, "A": 0, "B": 0, "C": 0}
        model_stats[key]["count"] += 1
        model_stats[key]["A"] += r.get("A", 0)
        model_stats[key]["B"] += r.get("B", 0)
        model_stats[key]["C"] += r.get("C", 0)

    for key, stats in sorted(model_stats.items()):
        parts = key.rsplit(" ", 1)
        model_name = parts[0] if len(parts) > 1 else key
        mode_name = parts[1].strip("()") if len(parts) > 1 else ""
        print(
            f"{model_name:<20} {mode_name:<10} {stats['count']:>8} "
            f"{stats['A']:>8} {stats['B']:>8} {stats['C']:>8}"
        )

    total_a = sum(r.get("A", 0) for r in results)
    total_b = sum(r.get("B", 0) for r in results)
    total_c = sum(r.get("C", 0) for r in results)
    print("-" * 62)
    print(f"{'TOTAL':<20} {'':<10} {len(results):>8} {total_a:>8} {total_b:>8} {total_c:>8}")
