"""Core image-analysis logic for the IRSTD-AutoLabel CLI."""
from __future__ import annotations

import math
from collections import deque
from pathlib import Path

from PIL import Image, ImageOps

MASK_THRESHOLD = 32

# Adaptive box sizing constants used throughout the annotation pipeline.
ADAPTIVE_MIN_SIZE = 6
ADAPTIVE_PADDING = 4
MIN_TARGET_PIXELS = 5


def load_image(path: Path) -> Image.Image:
    """Load image from path, handle EXIF rotation."""
    image = Image.open(path)
    image.load()
    return ImageOps.exif_transpose(image)


def prepare_mask(
    mask_image: Image.Image,
    target_size: tuple[int, int],
    resample: Image.Resampling = Image.Resampling.NEAREST,
) -> tuple[Image.Image, Image.Image]:
    """Convert mask to binary and grayscale, resize to target."""
    grayscale = ImageOps.autocontrast(mask_image.convert("L"))
    resized_grayscale = grayscale.resize(target_size, resample)
    binary_mask = resized_grayscale.point(
        lambda pixel: 255 if pixel >= MASK_THRESHOLD else 0, mode="L"
    )
    return binary_mask, resized_grayscale


def extract_connected_boxes(
    binary_mask: Image.Image,
    grayscale_image: Image.Image,
    source_type: str,
) -> list[dict]:
    """Extract connected components from binary mask using BFS."""
    width, height = binary_mask.size
    mask_pixels = binary_mask.load()
    grayscale_pixels = grayscale_image.load()
    visited = bytearray(width * height)
    boxes: list[dict] = []

    def pixel_index(x: int, y: int) -> int:
        return y * width + x

    component_index = 1

    for y in range(height):
        for x in range(width):
            index = pixel_index(x, y)

            if visited[index] or mask_pixels[x, y] == 0:
                continue

            queue: deque[tuple[int, int]] = deque([(x, y)])
            visited[index] = 1

            min_x = max_x = x
            min_y = max_y = y
            pixel_count = 0
            sum_x = 0.0
            sum_y = 0.0
            grayscale_sum = 0.0

            while queue:
                current_x, current_y = queue.popleft()
                pixel_count += 1
                min_x = min(min_x, current_x)
                max_x = max(max_x, current_x)
                min_y = min(min_y, current_y)
                max_y = max(max_y, current_y)
                sum_x += current_x
                sum_y += current_y
                grayscale_sum += float(grayscale_pixels[current_x, current_y])

                for neighbor_y in range(
                    max(0, current_y - 1), min(height - 1, current_y + 1) + 1
                ):
                    for neighbor_x in range(
                        max(0, current_x - 1), min(width - 1, current_x + 1) + 1
                    ):
                        neighbor_index = pixel_index(neighbor_x, neighbor_y)

                        if (
                            visited[neighbor_index]
                            or mask_pixels[neighbor_x, neighbor_y] == 0
                        ):
                            continue

                        visited[neighbor_index] = 1
                        queue.append((neighbor_x, neighbor_y))

            confidence = (
                grayscale_sum / (pixel_count * 255.0) if pixel_count else 0.0
            )
            box_width = max_x - min_x + 1
            box_height = max_y - min_y + 1
            center_x = (
                sum_x / pixel_count
                if pixel_count
                else min_x + (box_width / 2.0)
            )
            center_y = (
                sum_y / pixel_count
                if pixel_count
                else min_y + (box_height / 2.0)
            )

            boxes.append(
                {
                    "id": f"{source_type}-{component_index:04d}",
                    "source_type": source_type,
                    "x": float(min_x),
                    "y": float(min_y),
                    "width": float(box_width),
                    "height": float(box_height),
                    "center_x": round(center_x, 3),
                    "center_y": round(center_y, 3),
                    "pixel_count": pixel_count,
                    "confidence": (
                        round(confidence, 4) if source_type == "pred" else 1.0
                    ),
                }
            )
            component_index += 1

    boxes.sort(key=lambda item: (item["y"], item["x"]))
    return boxes


def evaluate_matches(
    ground_truth_boxes: list[dict],
    prediction_boxes: list[dict],
    threshold: float,
    strategy: str,
) -> dict:
    """Match predictions to ground truth using center distance."""
    candidate_pairs: list[dict] = []

    for prediction in prediction_boxes:
        for ground_truth in ground_truth_boxes:
            distance = math.hypot(
                prediction["center_x"] - ground_truth["center_x"],
                prediction["center_y"] - ground_truth["center_y"],
            )
            if distance <= threshold:
                candidate_pairs.append(
                    {
                        "gt_id": ground_truth["id"],
                        "pred_id": prediction["id"],
                        "distance": round(distance, 4),
                        "confidence": prediction.get("confidence", 0.0),
                    }
                )

    use_distance_first = strategy == "distance"

    def candidate_key(pair: dict) -> tuple:
        if use_distance_first:
            return (
                pair["distance"],
                -pair["confidence"],
                pair["pred_id"],
                pair["gt_id"],
            )
        return (
            -pair["confidence"],
            pair["distance"],
            pair["pred_id"],
            pair["gt_id"],
        )

    candidate_pairs.sort(key=candidate_key)

    matched_gt_ids: set[str] = set()
    matched_pred_ids: set[str] = set()
    matches: list[dict] = []

    for pair in candidate_pairs:
        if pair["gt_id"] in matched_gt_ids or pair["pred_id"] in matched_pred_ids:
            continue

        matched_gt_ids.add(pair["gt_id"])
        matched_pred_ids.add(pair["pred_id"])
        matches.append(pair)

    false_alarm_ids = [
        box["id"] for box in prediction_boxes if box["id"] not in matched_pred_ids
    ]
    miss_ids = [
        box["id"] for box in ground_truth_boxes if box["id"] not in matched_gt_ids
    ]

    return {
        "threshold": threshold,
        "strategy": strategy,
        "match_count": len(matches),
        "counts": {
            "A": len(matches),
            "B": len(false_alarm_ids),
            "C": len(miss_ids),
        },
        "matches": matches,
        "true_positive_ids": [match["pred_id"] for match in matches],
        "false_alarm_ids": false_alarm_ids,
        "miss_ids": miss_ids,
    }


def _normalize_box(box: dict) -> dict:
    """Normalize box fields into a consistent representation."""
    width = max(1.0, float(box.get("width", 1)))
    height = max(1.0, float(box.get("height", 1)))
    x = float(box.get("x", 0))
    y = float(box.get("y", 0))
    return {
        **box,
        "x": x,
        "y": y,
        "width": width,
        "height": height,
        "center_x": float(box.get("center_x", x + width / 2)),
        "center_y": float(box.get("center_y", y + height / 2)),
        "confidence": float(box.get("confidence", 0)),
        "pixel_count": int(box.get("pixel_count", max(1, round(width * height)))),
    }


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _merge_overlapping(boxes: list[dict]) -> list[dict]:
    """Union-Find merge of overlapping boxes within same category."""
    if len(boxes) < 2:
        return boxes

    n = len(boxes)
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        parent[find(i)] = find(j)

    for i in range(n):
        for j in range(i + 1, n):
            a, b = boxes[i], boxes[j]
            if (a["x"] < b["x"] + b["width"]
                    and a["x"] + a["width"] > b["x"]
                    and a["y"] < b["y"] + b["height"]
                    and a["y"] + a["height"] > b["y"]):
                union(i, j)

    groups: dict[int, list[int]] = {}
    for i in range(n):
        root = find(i)
        groups.setdefault(root, []).append(i)

    result = []
    for indices in groups.values():
        if len(indices) == 1:
            result.append(boxes[indices[0]])
            continue

        group = [boxes[i] for i in indices]
        min_x = min(b["x"] for b in group)
        min_y = min(b["y"] for b in group)
        max_x = max(b["x"] + b["width"] for b in group)
        max_y = max(b["y"] + b["height"] for b in group)
        cx = (min_x + max_x) / 2
        cy = (min_y + max_y) / 2
        first = group[0]
        max_adaptive = max(max(b["width"], b["height"]) for b in group)
        size = max(ADAPTIVE_MIN_SIZE, max_adaptive)
        half = size / 2

        result.append({
            **first,
            "x": round(cx - half, 3),
            "y": round(cy - half, 3),
            "width": round(size, 3),
            "height": round(size, 3),
            "center_x": round(cx, 3),
            "center_y": round(cy, 3),
            "pixel_count": max(1, round(size * size)),
        })

    return result


def _promote_bc_to_a(
    group_a: list[dict], group_b: list[dict], group_c: list[dict]
) -> tuple[list[dict], list[dict], list[dict]]:
    """Promote overlapping B/C pairs to A when targets are substantial."""
    promoted_pred_ids: set[str] = set()
    promoted_gt_ids: set[str] = set()

    for b_box in group_b:
        for c_box in group_c:
            if b_box["id"] in promoted_pred_ids or c_box["id"] in promoted_gt_ids:
                continue
            if not (b_box["x"] < c_box["x"] + c_box["width"]
                    and b_box["x"] + b_box["width"] > c_box["x"]
                    and b_box["y"] < c_box["y"] + c_box["height"]
                    and b_box["y"] + b_box["height"] > c_box["y"]):
                continue
            b_pixels = b_box.get("pixel_count", 0)
            c_pixels = c_box.get("pixel_count", 0)
            if b_pixels < MIN_TARGET_PIXELS or c_pixels < MIN_TARGET_PIXELS:
                continue
            promoted_pred_ids.add(b_box["id"])
            promoted_gt_ids.add(c_box["id"])

    if promoted_pred_ids:
        promoted_b = [{**b, "source_type": "pred"} for b in group_b if b["id"] in promoted_pred_ids]
        kept_b = [b for b in group_b if b["id"] not in promoted_pred_ids]
        group_a = group_a + promoted_b
        group_b = kept_b
        group_c = [c for c in group_c if c["id"] not in promoted_gt_ids]

    return group_a, group_b, group_c


def _absorb_ab_overlap(
    group_a: list[dict], group_b: list[dict]
) -> tuple[list[dict], list[dict]]:
    """Merge overlapping A/B pairs: expand A to cover B, remove B."""
    absorbed_ids: set[str] = set()

    for ai, a_box in enumerate(group_a):
        for b_box in group_b:
            if b_box["id"] in absorbed_ids:
                continue
            if not (a_box["x"] < b_box["x"] + b_box["width"]
                    and a_box["x"] + a_box["width"] > b_box["x"]
                    and a_box["y"] < b_box["y"] + b_box["height"]
                    and a_box["y"] + a_box["height"] > b_box["y"]):
                continue

            min_x = min(a_box["x"], b_box["x"])
            min_y = min(a_box["y"], b_box["y"])
            max_x = max(a_box["x"] + a_box["width"], b_box["x"] + b_box["width"])
            max_y = max(a_box["y"] + a_box["height"], b_box["y"] + b_box["height"])
            group_a[ai] = {
                **a_box,
                "x": min_x,
                "y": min_y,
                "width": max_x - min_x,
                "height": max_y - min_y,
                "center_x": (min_x + max_x) / 2,
                "center_y": (min_y + max_y) / 2,
                "pixel_count": max(1, round((max_x - min_x) * (max_y - min_y))),
            }
            absorbed_ids.add(b_box["id"])

    if absorbed_ids:
        group_b = [b for b in group_b if b["id"] not in absorbed_ids]

    return group_a, group_b


def _adaptive_boxes(
    boxes: list[dict], img_w: int, img_h: int, padding: int = ADAPTIVE_PADDING
) -> list[dict]:
    """Adaptive box sizing: square, padded, min size, overlap resolution."""
    extra_padding = max(0, padding)
    min_size = ADAPTIVE_MIN_SIZE

    result = []
    for box in boxes:
        raw_w = float(box.get("width", 1))
        raw_h = float(box.get("height", 1))
        base_size = max(raw_w, raw_h)
        adaptive_size = max(base_size + extra_padding, min_size)

        cx = float(box.get("center_x", box.get("x", 0) + raw_w / 2))
        cy = float(box.get("center_y", box.get("y", 0) + raw_h / 2))
        half = adaptive_size / 2
        x = _clamp(cx - half, 0, max(0, img_w - adaptive_size))
        y = _clamp(cy - half, 0, max(0, img_h - adaptive_size))

        result.append({
            **box,
            "x": round(x, 3),
            "y": round(y, 3),
            "width": round(adaptive_size, 3),
            "height": round(adaptive_size, 3),
            "center_x": round(cx, 3),
            "center_y": round(cy, 3),
            "pixel_count": max(1, round(adaptive_size * adaptive_size)),
        })

    # Resolve overlaps by shrinking colliding boxes equally
    changed = True
    while changed:
        changed = False
        for i in range(len(result)):
            for j in range(i + 1, len(result)):
                if result[i].get("source_type") != result[j].get("source_type"):
                    continue
                a, b = result[i], result[j]
                if not (a["x"] < b["x"] + b["width"]
                        and a["x"] + a["width"] > b["x"]
                        and a["y"] < b["y"] + b["height"]
                        and a["y"] + a["height"] > b["y"]):
                    continue
                for idx in (i, j):
                    box = result[idx]
                    if box["width"] <= min_size:
                        continue
                    new_size = box["width"] - 1
                    half = new_size / 2
                    bcx = box["x"] + box["width"] / 2
                    bcy = box["y"] + box["height"] / 2
                    result[idx] = {
                        **box,
                        "width": round(new_size, 3),
                        "height": round(new_size, 3),
                        "x": round(_clamp(bcx - half, 0, max(0, img_w - new_size)), 3),
                        "y": round(_clamp(bcy - half, 0, max(0, img_h - new_size)), 3),
                        "pixel_count": max(1, round(new_size * new_size)),
                    }
                    changed = True

    return result


def analyze_prediction(
    gt_image: Image.Image,
    pred_image: Image.Image,
    threshold: float = 3.0,
    strategy: str = "confidence",
    adaptive_padding: int = ADAPTIVE_PADDING,
    mask_resample: Image.Resampling = Image.Resampling.NEAREST,
) -> dict:
    """
    Analyze prediction against ground truth with full post-processing.

    Classification pipeline:
      1. Extract connected components (BFS)
      2. Normalize boxes
      3. Match by center distance
      4. Initial classification (A/B/C)
      5. Promote overlapping B/C → A
      6. Absorb overlapping A/B → expand A
      7. Merge overlapping boxes within each category
      8. Adaptive box sizing (square, padded, min size)

    Returns:
        {
            "image_size": (width, height),
            "gt_boxes": [...],
            "pred_boxes": [...],
            "evaluation": {...},
            "classified_boxes": {"A": [...], "B": [...], "C": [...]}
        }
    """
    img_w, img_h = pred_image.size
    target_size = (img_w, img_h)

    # 1. Extract connected components
    gt_binary, gt_gray = prepare_mask(gt_image, target_size, mask_resample)
    pred_binary, pred_gray = prepare_mask(pred_image, target_size, mask_resample)
    gt_boxes = extract_connected_boxes(gt_binary, gt_gray, "gt")
    pred_boxes = extract_connected_boxes(pred_binary, pred_gray, "pred")

    # 2. Normalize boxes
    norm_gt = [_normalize_box(b) for b in gt_boxes]
    norm_pred = [_normalize_box(b) for b in pred_boxes]

    # 3. Match by center distance
    evaluation = evaluate_matches(norm_gt, norm_pred, threshold, strategy)

    # 4. Initial classification
    tp_ids = set(evaluation["true_positive_ids"])
    fa_ids = set(evaluation["false_alarm_ids"])
    miss_ids = set(evaluation["miss_ids"])

    # A: matched predictions (use GT geometry for accuracy)
    gt_map = {b["id"]: b for b in norm_gt}
    pred_map = {b["id"]: b for b in norm_pred}
    group_a = []
    for match in evaluation["matches"]:
        pred_box = pred_map[match["pred_id"]]
        gt_box = gt_map[match["gt_id"]]
        base = gt_box if gt_box else pred_box
        group_a.append({
            **base,
            "id": pred_box["id"],
            "source_type": "pred",
            "matched_gt_id": match["gt_id"],
            "distance": match["distance"],
        })

    # B: unmatched predictions (false alarms)
    group_b = [b for b in norm_pred if b["id"] in fa_ids]

    # C: unmatched ground truth (misses)
    group_c = [b for b in norm_gt if b["id"] in miss_ids]

    # 5. Promote overlapping B/C → A
    group_a, group_b, group_c = _promote_bc_to_a(group_a, group_b, group_c)

    # 6. Absorb overlapping A/B → expand A
    group_a, group_b = _absorb_ab_overlap(group_a, group_b)

    # 7. Merge overlapping boxes within each category
    group_a = _merge_overlapping(group_a)
    group_b = _merge_overlapping(group_b)
    group_c = _merge_overlapping(group_c)

    # 8. Adaptive box sizing
    group_a = _adaptive_boxes(group_a, img_w, img_h, adaptive_padding)
    group_b = _adaptive_boxes(group_b, img_w, img_h, adaptive_padding)
    group_c = _adaptive_boxes(group_c, img_w, img_h, adaptive_padding)

    # Sort by position
    sort_key = lambda b: (b["y"], b["x"])
    group_a.sort(key=sort_key)
    group_b.sort(key=sort_key)
    group_c.sort(key=sort_key)

    classified = {"A": group_a, "B": group_b, "C": group_c}

    return {
        "image_size": target_size,
        "gt_boxes": norm_gt,
        "pred_boxes": norm_pred,
        "evaluation": evaluation,
        "classified_boxes": classified,
    }


def analyze_original(
    gt_image: Image.Image,
    adaptive_padding: int = ADAPTIVE_PADDING,
    mask_resample: Image.Resampling = Image.Resampling.NEAREST,
) -> dict:
    """
    Analyze ground truth only (for original mode).

    Returns:
        {
            "image_size": (width, height),
            "gt_boxes": [...]
        }
    """
    img_w, img_h = gt_image.size
    target_size = (img_w, img_h)

    gt_binary, gt_gray = prepare_mask(gt_image, target_size, mask_resample)
    gt_boxes = extract_connected_boxes(gt_binary, gt_gray, "gt")

    # Normalize and apply adaptive sizing
    norm_gt = [_normalize_box(b) for b in gt_boxes]
    norm_gt = _adaptive_boxes(norm_gt, img_w, img_h, adaptive_padding)
    norm_gt.sort(key=lambda b: (b["y"], b["x"]))

    return {
        "image_size": target_size,
        "gt_boxes": norm_gt,
    }
