"""Visualization renderer for batch labeling."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

# Color definitions (RGB)
DEFAULT_COLORS = {
    "A": (255, 0, 0),      # Red - True Positive
    "B": (255, 215, 0),    # Yellow - False Alarm
    "C": (0, 191, 255),    # Blue - Miss
    "GT": (255, 0, 0),     # Red - Ground Truth (original mode)
}

COLORS = DEFAULT_COLORS

# Zoom settings
ZOOM_PANEL_SIZE = 188
DEFAULT_ZOOM_BORDER_WIDTH = 8
DEFAULT_PANEL_PADDING = 2

# Longest-side resolution used for exported visualizations.
EXPORT_LONGEST_SIDE = 960

# Proximity threshold for grouping nearby targets into one zoom panel
# (in pixels at export resolution). Targets whose centers are within this
# distance AND belong to the same category share a single zoom panel.
ZOOM_GROUP_DISTANCE = 20

# Canonical slot order for zoom panels (3x3 grid)
CANONICAL_SLOT_ORDER = [
    (0, 0), (0, 1), (0, 2),
    (1, 0),
    (2, 0), (2, 1), (2, 2),
]


def compute_adaptive_zoom(
    box: dict,
    panel_size: int = ZOOM_PANEL_SIZE,
    panel_padding: int = DEFAULT_PANEL_PADDING,
) -> tuple[float, int]:
    """
    Compute adaptive zoom factor and source window for a target.

    Logic:
      - available = panel_size - 2 * panel_padding
      - adaptive_zoom = available / display_size (clamped to [2, 8])
      - source_window = panel_size / adaptive_zoom

    This ensures the target fits within the panel with the specified
    padding on each side. Smaller targets get higher zoom (up to 8x),
    larger targets get lower zoom so the full shape is visible.

    Args:
        box: Target box with width/height
        panel_size: Zoom panel size in pixels
        panel_padding: Padding between target edge and panel edge

    Returns:
        (adaptive_zoom, source_window)
    """
    display_size = max(box.get("width", 1), box.get("height", 1))
    available = panel_size - 2 * max(0, panel_padding)
    adaptive_zoom = max(2.0, min(8.0, available / max(display_size, 1)))
    source_window = round(panel_size / adaptive_zoom)
    return adaptive_zoom, source_window


def _group_nearby_boxes(
    boxes: list[dict],
    distance: int = ZOOM_GROUP_DISTANCE,
) -> list[dict]:
    """
    Group nearby boxes so close targets share one zoom panel.

    Uses simple single-linkage clustering: boxes whose centers are within
    `distance` pixels of each other are merged into a single group.  The
    merged entry uses a virtual bounding box that encompasses all members
    and carries a ``_group`` list with the original boxes.

    Args:
        boxes: List of box dicts (must have center_x, center_y).
        distance: Maximum center-to-center distance for grouping.

    Returns:
        List of zoom entries (single-box or merged group).
    """
    if len(boxes) <= 1:
        return list(boxes)

    remaining = list(range(len(boxes)))
    groups: list[list[int]] = []

    while remaining:
        seed = remaining.pop(0)
        group = [seed]
        changed = True
        while changed:
            changed = False
            for idx in remaining[:]:
                for member in group:
                    dx = boxes[idx]["center_x"] - boxes[member]["center_x"]
                    dy = boxes[idx]["center_y"] - boxes[member]["center_y"]
                    if (dx * dx + dy * dy) ** 0.5 <= distance:
                        group.append(idx)
                        remaining.remove(idx)
                        changed = True
                        break
        groups.append(group)

    result: list[dict] = []
    for grp in groups:
        if len(grp) == 1:
            result.append(boxes[grp[0]])
        else:
            member_boxes = [boxes[i] for i in grp]
            result.append(_make_group_box(member_boxes))
    return result


def _make_group_box(boxes: list[dict]) -> dict:
    """Create a virtual bounding box that encompasses all *boxes*."""
    min_x = min(b["x"] for b in boxes)
    min_y = min(b["y"] for b in boxes)
    max_x = max(b["x"] + b["width"] for b in boxes)
    max_y = max(b["y"] + b["height"] for b in boxes)
    w = max_x - min_x
    h = max_y - min_y
    return {
        "x": min_x,
        "y": min_y,
        "width": w,
        "height": h,
        "center_x": min_x + w / 2,
        "center_y": min_y + h / 2,
        "id": boxes[0].get("id", ""),
        "_group": boxes,
    }


def draw_zoom_crop(
    source_image: Image.Image,
    box: dict,
    all_boxes: list[dict],
    panel_size: int = ZOOM_PANEL_SIZE,
    panel_padding: int = DEFAULT_PANEL_PADDING,
    brightness: float = 1.0,
    contrast: float = 1.0,
    show_crosshair: bool = False,
    zoom_resample: Image.Resampling = Image.Resampling.NEAREST,
    output_resample: Image.Resampling = Image.Resampling.NEAREST,
) -> Image.Image:
    """
    Create zoom crop panel for a single target with adaptive zoom.

    Args:
        source_image: Source image to crop from
        box: Target box dict with x, y, width, height, center_x, center_y
        all_boxes: All boxes (for blacking out neighbors)
        panel_size: Output panel size
        panel_padding: Padding between target edge and panel edge
        brightness: Brightness adjustment factor
        contrast: Contrast adjustment factor
        show_crosshair: Whether to draw crosshair lines

    Returns:
        PIL Image of zoomed crop
    """
    adaptive_zoom, source_window = compute_adaptive_zoom(box, panel_size, panel_padding)
    zoom = round(adaptive_zoom)

    source_width, source_height = source_image.size
    zoomed_width = max(1, round(source_width * zoom))
    zoomed_height = max(1, round(source_height * zoom))
    zoomed_crop_size = source_window * zoom

    # Create zoomed image
    zoomed = source_image.resize((zoomed_width, zoomed_height), zoom_resample)

    # Apply brightness/contrast
    if brightness != 1.0 or contrast != 1.0:
        zoomed = _adjust_brightness_contrast(zoomed, brightness, contrast)

    # Black out neighboring targets (skip members of the current group)
    zoomed_rgba = zoomed.convert("RGBA")
    black_overlay = Image.new("RGBA", zoomed_rgba.size, (0, 0, 0, 255))
    group_ids = {b.get("id") for b in box.get("_group", [box])}

    for other in all_boxes:
        if other.get("id") in group_ids:
            continue
        ox = int(other["x"] * zoom)
        oy = int(other["y"] * zoom)
        ow = int(other["width"] * zoom)
        oh = int(other["height"] * zoom)

        # Check bounds
        if ox + ow <= 0 or oy + oh <= 0 or ox >= zoomed_width or oy >= zoomed_height:
            continue

        # Create mask for this box region
        mask = Image.new("L", zoomed_rgba.size, 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.rectangle(
            [max(0, ox), max(0, oy), min(zoomed_width, ox + ow), min(zoomed_height, oy + oh)],
            fill=255,
        )
        zoomed_rgba = Image.composite(black_overlay, zoomed_rgba, mask)

    # Crop center region
    crop_center_x = box["center_x"] * zoom
    crop_center_y = box["center_y"] * zoom

    raw_start_x = round(crop_center_x - zoomed_crop_size / 2)
    raw_start_y = round(crop_center_y - zoomed_crop_size / 2)

    source_x = max(0, raw_start_x)
    source_y = max(0, raw_start_y)
    dest_x = max(0, -raw_start_x)
    dest_y = max(0, -raw_start_y)

    source_crop_width = max(
        0, min(zoomed_width - source_x, zoomed_crop_size - dest_x)
    )
    source_crop_height = max(
        0, min(zoomed_height - source_y, zoomed_crop_size - dest_y)
    )

    # Create crop canvas
    crop = Image.new("RGBA", (zoomed_crop_size, zoomed_crop_size), (0, 0, 0, 255))

    if source_crop_width > 0 and source_crop_height > 0:
        cropped_region = zoomed_rgba.crop(
            (source_x, source_y, source_x + source_crop_width, source_y + source_crop_height)
        )
        crop.paste(cropped_region, (dest_x, dest_y))

    # Resize to panel size
    result = crop.resize((panel_size, panel_size), output_resample)

    # Draw crosshair (disabled by default for clean figure export).
    if show_crosshair:
        draw = ImageDraw.Draw(result)
        draw.line(
            [(panel_size // 2, 0), (panel_size // 2, panel_size)],
            fill=(255, 255, 255, 180),
            width=1,
        )
        draw.line(
            [(0, panel_size // 2), (panel_size, panel_size // 2)],
            fill=(255, 255, 255, 180),
            width=1,
        )

    return result.convert("RGB")


def _adjust_brightness_contrast(
    image: Image.Image, brightness: float, contrast: float
) -> Image.Image:
    """Adjust brightness and contrast of an image."""
    # Simple brightness/contrast adjustment
    from PIL import ImageEnhance

    if brightness != 1.0:
        enhancer = ImageEnhance.Brightness(image)
        image = enhancer.enhance(brightness)

    if contrast != 1.0:
        enhancer = ImageEnhance.Contrast(image)
        image = enhancer.enhance(contrast)

    return image


def mirror_slot_for_corner(slot: tuple[int, int], corner: str) -> tuple[int, int]:
    """Mirror slot position based on corner."""
    row, col = slot
    if corner == "top-right":
        return (row, 2 - col)
    elif corner == "bottom-right":
        return (2 - row, 2 - col)
    elif corner == "bottom-left":
        return (2 - row, col)
    return slot


def build_candidate_slots(
    main_width: int, main_height: int, panel_size: int, corner: str
) -> list[tuple[int, int, int, int]]:
    """Build candidate slot positions for zoom panels."""
    region_size = panel_size * 3

    anchors = {
        "top-left": (0, 0),
        "top-right": (main_width - region_size, 0),
        "bottom-right": (main_width - region_size, main_height - region_size),
        "bottom-left": (0, main_height - region_size),
    }

    anchor_x, anchor_y = anchors[corner]

    slots = []
    for slot in CANONICAL_SLOT_ORDER:
        mirrored = mirror_slot_for_corner(slot, corner)
        x = anchor_x + mirrored[1] * panel_size
        y = anchor_y + mirrored[0] * panel_size
        slots.append((x, y, panel_size, panel_size))

    return slots


def has_intersection(
    rect1: tuple[int, int, int, int], rect2: tuple[int, int, int, int]
) -> bool:
    """Check if two rectangles intersect."""
    x1, y1, w1, h1 = rect1
    x2, y2, w2, h2 = rect2

    overlap_x = max(0, min(x1 + w1, x2 + w2) - max(x1, x2))
    overlap_y = max(0, min(y1 + h1, y2 + h2) - max(y1, y2))

    return overlap_x > 0 and overlap_y > 0


def expand_rect(
    rect: tuple[int, int, int, int], padding: int
) -> tuple[int, int, int, int]:
    """Expand rectangle by padding."""
    x, y, w, h = rect
    return (x - padding, y - padding, w + padding * 2, h + padding * 2)


def is_inside_image(
    rect: tuple[int, int, int, int],
    main_x: int,
    main_y: int,
    main_width: int,
    main_height: int,
) -> bool:
    """Check if rectangle is inside image bounds."""
    x, y, w, h = rect
    return (
        x >= main_x
        and y >= main_y
        and x + w <= main_x + main_width
        and y + h <= main_y + main_height
    )


def pick_zoom_placements(
    zoom_entries: list[dict],
    main_width: int,
    main_height: int,
    panel_size: int,
    target_rects: list[tuple[int, int, int, int]],
    scale: float,
) -> list[dict]:
    """
    Pick optimal placements for zoom panels.

    Returns list of {box, placement: (x, y, w, h), category}
    """
    corners = ["top-left", "top-right", "bottom-right", "bottom-left"]
    best_placements = []

    for corner in corners:
        candidate_slots = build_candidate_slots(main_width, main_height, panel_size, corner)

        # Filter slots that don't overlap with targets
        valid_slots = []
        for slot in candidate_slots:
            if not any(has_intersection(slot, tr) for tr in target_rects):
                valid_slots.append(slot)

        # Assign entries to slots
        placements = []
        for i, entry in enumerate(zoom_entries[: len(valid_slots)]):
            placements.append(
                {
                    **entry,
                    "placement": valid_slots[i],
                }
            )

        # Resolve cross-category spacing
        placements = _resolve_category_spacing(placements, target_rects)

        if len(placements) > len(best_placements):
            best_placements = placements

        # If all entries placed, use this corner
        if len(placements) == len(zoom_entries):
            break

    return best_placements


def _resolve_category_spacing(
    placements: list[dict], target_rects: list[tuple[int, int, int, int]]
) -> list[dict]:
    """Resolve spacing between A and B category zoom panels."""
    if len(placements) < 2:
        return placements

    border_gap = max(0, DEFAULT_ZOOM_BORDER_WIDTH // 2 - 1)

    # Check if categories overlap
    for i, p1 in enumerate(placements):
        for j, p2 in enumerate(placements):
            if i >= j:
                continue
            if p1.get("category") == p2.get("category"):
                continue

            rect1 = expand_rect(p1["placement"], border_gap)
            rect2 = expand_rect(p2["placement"], border_gap)

            if has_intersection(rect1, rect2):
                # Try to shift one of them
                return _try_shift_placements(placements, target_rects)

    return placements


def _try_shift_placements(
    placements: list[dict], target_rects: list[tuple[int, int, int, int]]
) -> list[dict]:
    """Try to shift placements to resolve overlaps."""
    # Simple heuristic: shift B category panels
    border_gap = max(0, DEFAULT_ZOOM_BORDER_WIDTH // 2 - 1)

    for shift_x in range(-border_gap, border_gap + 1):
        for shift_y in range(-border_gap, border_gap + 1):
            shifted = []
            for p in placements:
                if p.get("category") == "B":
                    x, y, w, h = p["placement"]
                    new_placement = (x + shift_x, y + shift_y, w, h)
                    shifted.append({**p, "placement": new_placement})
                else:
                    shifted.append(p)

            # Check if shift resolves all overlaps
            valid = True
            for i, p1 in enumerate(shifted):
                for j, p2 in enumerate(shifted):
                    if i >= j:
                        continue
                    if p1.get("category") == p2.get("category"):
                        continue

                    rect1 = expand_rect(p1["placement"], border_gap)
                    rect2 = expand_rect(p2["placement"], border_gap)

                    if has_intersection(rect1, rect2):
                        valid = False
                        break
                if not valid:
                    break

            if valid:
                return shifted

    return placements


def _scale_box(box: dict, scale: float) -> dict:
    """Scale a single box by the given factor."""
    return {
        **box,
        "x": box["x"] * scale,
        "y": box["y"] * scale,
        "width": box["width"] * scale,
        "height": box["height"] * scale,
        "center_x": box["center_x"] * scale,
        "center_y": box["center_y"] * scale,
    }


def _scale_boxes(boxes: list[dict], scale: float) -> list[dict]:
    """Scale a list of boxes."""
    return [_scale_box(b, scale) for b in boxes]


def _scale_classified_boxes(classified: dict, scale: float) -> dict:
    """Scale classified boxes dict {A: [...], B: [...], C: [...]}."""
    return {k: _scale_boxes(v, scale) for k, v in classified.items()}


def render_prediction_mode(
    base_image: Image.Image,
    classified_boxes: dict,
    stroke_width: int = 1,
    brightness: float = 1.0,
    contrast: float = 1.0,
    show_c_boxes: bool = True,
    panel_padding: int = DEFAULT_PANEL_PADDING,
    base_resample: Image.Resampling = Image.Resampling.LANCZOS,
    zoom_resample: Image.Resampling = Image.Resampling.NEAREST,
    panel_resample: Image.Resampling = Image.Resampling.NEAREST,
    colors: dict[str, tuple[int, int, int]] | None = None,
) -> Image.Image:
    """
    Render prediction mode visualization.

    Args:
        base_image: Prediction image (base)
        classified_boxes: {"A": [...], "B": [...], "C": [...]}
        stroke_width: Small box stroke width in pixels (at 960px scale)
        brightness: Brightness adjustment
        contrast: Contrast adjustment
        show_c_boxes: Whether to show C (miss) boxes
        panel_padding: Padding between target edge and zoom panel edge

    Returns:
        Rendered image with zoom panels
    """
    # Adjust brightness/contrast
    if brightness != 1.0 or contrast != 1.0:
        base_image = _adjust_brightness_contrast(base_image, brightness, contrast)

    # Upscale to the configured export resolution.
    orig_w, orig_h = base_image.size
    longest = max(orig_w, orig_h)
    if longest != EXPORT_LONGEST_SIDE:
        scale = EXPORT_LONGEST_SIDE / longest
        new_w = round(orig_w * scale)
        new_h = round(orig_h * scale)
        base_image = base_image.resize((new_w, new_h), base_resample)
        # Scale boxes to match new resolution
        classified_boxes = _scale_classified_boxes(classified_boxes, scale)
        # Scale stroke width proportionally
        stroke_width = max(1, round(stroke_width * scale))

    result = base_image.copy().convert("RGBA")
    draw = ImageDraw.Draw(result)

    a_boxes = classified_boxes.get("A", [])
    b_boxes = classified_boxes.get("B", [])
    c_boxes = classified_boxes.get("C", []) if show_c_boxes else []
    render_colors = colors or DEFAULT_COLORS

    # Draw C boxes (miss - blue, no zoom)
    for box in c_boxes:
        _draw_box(draw, box, render_colors["C"], stroke_width)

    # Group nearby targets for shared zoom panels
    grouped_a = _group_nearby_boxes(a_boxes)
    grouped_b = _group_nearby_boxes(b_boxes)
    all_boxes = a_boxes + b_boxes + c_boxes

    # Draw A boxes (red) — one box per group
    for box in grouped_a:
        _draw_box(draw, box, render_colors["A"], stroke_width)

    # Draw B boxes (yellow) — one box per group
    for box in grouped_b:
        _draw_box(draw, box, render_colors["B"], stroke_width)

    # Create zoom panels for grouped A and B
    zoom_entries = []
    for box in grouped_a:
        zoom_img = draw_zoom_crop(
            base_image, box, all_boxes, panel_padding=panel_padding,
            brightness=brightness, contrast=contrast,
            zoom_resample=zoom_resample,
            output_resample=panel_resample,
        )
        zoom_entries.append({"box": box, "image": zoom_img, "category": "A"})

    for box in grouped_b:
        zoom_img = draw_zoom_crop(
            base_image, box, all_boxes, panel_padding=panel_padding,
            brightness=brightness, contrast=contrast,
            zoom_resample=zoom_resample,
            output_resample=panel_resample,
        )
        zoom_entries.append({"box": box, "image": zoom_img, "category": "B"})

    # Place zoom panels (always use DEFAULT_ZOOM_BORDER_WIDTH for zoom borders)
    if zoom_entries:
        result = _place_zoom_panels(
            result,
            zoom_entries,
            a_boxes + b_boxes + c_boxes,
            resample=panel_resample,
            colors=render_colors,
        )

    return result.convert("RGB")


def render_original_mode(
    base_image: Image.Image,
    gt_boxes: list[dict],
    stroke_width: int = 1,
    brightness: float = 1.0,
    contrast: float = 1.0,
    panel_padding: int = DEFAULT_PANEL_PADDING,
    base_resample: Image.Resampling = Image.Resampling.LANCZOS,
    zoom_resample: Image.Resampling = Image.Resampling.NEAREST,
    panel_resample: Image.Resampling = Image.Resampling.NEAREST,
    colors: dict[str, tuple[int, int, int]] | None = None,
) -> Image.Image:
    """
    Render original mode visualization.

    Args:
        base_image: Original image (base)
        gt_boxes: Ground truth boxes
        stroke_width: Small box stroke width in pixels (at 960px scale)
        brightness: Brightness adjustment
        contrast: Contrast adjustment
        panel_padding: Padding between target edge and zoom panel edge

    Returns:
        Rendered image with zoom panels
    """
    # Adjust brightness/contrast
    if brightness != 1.0 or contrast != 1.0:
        base_image = _adjust_brightness_contrast(base_image, brightness, contrast)

    # Upscale to the configured export resolution.
    orig_w, orig_h = base_image.size
    longest = max(orig_w, orig_h)
    if longest != EXPORT_LONGEST_SIDE:
        scale = EXPORT_LONGEST_SIDE / longest
        new_w = round(orig_w * scale)
        new_h = round(orig_h * scale)
        base_image = base_image.resize((new_w, new_h), base_resample)
        # Scale boxes to match new resolution
        gt_boxes = _scale_boxes(gt_boxes, scale)
        # Scale stroke width proportionally
        stroke_width = max(1, round(stroke_width * scale))

    result = base_image.copy().convert("RGBA")
    draw = ImageDraw.Draw(result)
    render_colors = colors or DEFAULT_COLORS

    # Group nearby targets for shared zoom panels
    grouped_gt = _group_nearby_boxes(gt_boxes)

    # Draw GT boxes (red) — one box per group
    for box in grouped_gt:
        _draw_box(draw, box, render_colors["GT"], stroke_width)

    # Create zoom panels for grouped GT boxes
    zoom_entries = []
    for box in grouped_gt:
        zoom_img = draw_zoom_crop(
            base_image, box, gt_boxes, panel_padding=panel_padding,
            brightness=brightness, contrast=contrast,
            zoom_resample=zoom_resample,
            output_resample=panel_resample,
        )
        zoom_entries.append({"box": box, "image": zoom_img, "category": "GT"})

    # Place zoom panels (always use DEFAULT_ZOOM_BORDER_WIDTH for zoom borders)
    if zoom_entries:
        result = _place_zoom_panels(
            result,
            zoom_entries,
            gt_boxes,
            resample=panel_resample,
            colors=render_colors,
        )

    return result.convert("RGB")


def _draw_box(
    draw: ImageDraw.ImageDraw,
    box: dict,
    color: tuple[int, int, int],
    stroke_width: int,
) -> None:
    """Draw a single bounding box."""
    x = int(box["x"])
    y = int(box["y"])
    w = int(box["width"])
    h = int(box["height"])

    # Draw rectangle outline
    for i in range(stroke_width):
        draw.rectangle(
            [x - i, y - i, x + w + i, y + h + i],
            outline=color,
        )


def _place_zoom_panels(
    base_image: Image.Image,
    zoom_entries: list[dict],
    all_boxes: list[dict],
    border_width: int = DEFAULT_ZOOM_BORDER_WIDTH,
    resample: Image.Resampling = Image.Resampling.NEAREST,
    colors: dict[str, tuple[int, int, int]] | None = None,
) -> Image.Image:
    """Place zoom panels on the base image."""
    main_width, main_height = base_image.size
    panel_size = min(main_width, main_height) * 5 // 16

    # Calculate scale for target rects
    scale = 1.0  # Already in pixel coordinates

    # Build target rects (forbidden zones)
    target_rects = []
    for box in all_boxes:
        x = int(box["x"])
        y = int(box["y"])
        w = int(box["width"])
        h = int(box["height"])
        target_rects.append((x, y, w, h))

    # Pick placements
    placements = pick_zoom_placements(
        zoom_entries, main_width, main_height, panel_size, target_rects, scale
    )

    # Create result image
    result = base_image.copy().convert("RGBA")

    # Place zoom panels
    render_colors = colors or DEFAULT_COLORS
    for entry in placements:
        x, y, w, h = entry["placement"]
        zoom_img = entry["image"].resize((w, h), resample)

        # Paste zoom image
        result.paste(zoom_img.convert("RGBA"), (x, y))

        # Draw border on overlay
        color = render_colors.get(entry["category"], (255, 255, 255))
        overlay = Image.new("RGBA", (main_width, main_height), (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay)

        # Determine which edges touch the image boundary
        touches_left = x <= 0
        touches_top = y <= 0
        touches_right = x + w >= main_width
        touches_bottom = y + h >= main_height

        inset_left = border_width // 2 if touches_left else 1
        inset_top = border_width // 2 if touches_top else 1
        inset_right = border_width // 2 if touches_right else 1
        inset_bottom = border_width // 2 if touches_bottom else 1

        overlay_draw.rectangle(
            [x + inset_left, y + inset_top, x + w - inset_right - 1, y + h - inset_bottom - 1],
            outline=color,
            width=border_width,
        )

        # Composite overlay
        result = Image.alpha_composite(result, overlay)

    return result


def render_task(
    task: dict,
    analysis_result: dict,
    stroke_width: int = 1,
    brightness: float = 1.0,
    contrast: float = 1.0,
    panel_padding: int = DEFAULT_PANEL_PADDING,
    base_resample: Image.Resampling = Image.Resampling.LANCZOS,
    zoom_resample: Image.Resampling = Image.Resampling.NEAREST,
    panel_resample: Image.Resampling = Image.Resampling.NEAREST,
    colors: dict[str, tuple[int, int, int]] | None = None,
) -> Image.Image:
    """
    Render visualization for a single task.

    Args:
        task: Task dict with mode, original, gt, prediction paths
        analysis_result: Result from core.analyze_prediction or core.analyze_original
        stroke_width: Small box stroke width (zoom border always 4px)
        brightness: Brightness adjustment
        contrast: Contrast adjustment
        panel_padding: Padding between target edge and zoom panel edge

    Returns:
        Rendered image
    """
    mode = task.get("mode", "prediction")

    if mode == "original":
        base_image = load_image(task["original"])
        gt_boxes = analysis_result.get("gt_boxes", [])
        return render_original_mode(
            base_image,
            gt_boxes,
            stroke_width,
            brightness,
            contrast,
            panel_padding,
            base_resample,
            zoom_resample,
            panel_resample,
            colors,
        )
    else:
        base_image = load_image(task["prediction"])
        classified_boxes = analysis_result.get("classified_boxes", {"A": [], "B": [], "C": []})
        return render_prediction_mode(
            base_image,
            classified_boxes,
            stroke_width,
            brightness,
            contrast,
            show_c_boxes=True,
            panel_padding=panel_padding,
            base_resample=base_resample,
            zoom_resample=zoom_resample,
            panel_resample=panel_resample,
            colors=colors,
        )


def load_image(path: Path) -> Image.Image:
    """Load image from path."""
    from PIL import ImageOps

    image = Image.open(path)
    image.load()
    return ImageOps.exif_transpose(image)
