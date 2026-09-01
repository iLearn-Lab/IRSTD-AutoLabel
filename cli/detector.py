"""Auto-detect directory structure and build task lists."""
from __future__ import annotations

import re
from pathlib import Path

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}


def is_image(path: Path) -> bool:
    return path.suffix.lower() in IMAGE_EXTENSIONS


def list_images(directory: Path, recursive: bool = False) -> list[Path]:
    """List image files in directory."""
    if recursive:
        return sorted([f for f in directory.rglob("*") if f.is_file() and is_image(f)])
    return sorted([f for f in directory.iterdir() if f.is_file() and is_image(f)])


def detect_structure(input_dir: Path) -> dict:
    """
    Detect directory structure type and return metadata.

    Returns:
        {
            "type": "standard" | "sota_flat" | "numbered_flat",
            "input_dir": Path,
            "originals": {stem: path},
            "gt": {stem: path},
            "predictions": {source: {stem: path}},
            "sources": [source_name, ...]
        }
    """
    input_dir = input_dir.resolve()

    # Check for standard structure (Original/ and GT/ subdirectories)
    original_dir = input_dir / "Original"
    gt_dir = input_dir / "GT"

    if original_dir.is_dir() and gt_dir.is_dir():
        return _detect_standard_structure(input_dir, original_dir, gt_dir)

    # Check for flat structure with numbered prefixes
    images = list_images(input_dir)
    if not images:
        raise ValueError(f"No images found in {input_dir}")

    # Check sota_flat pattern: 0_yuan_*, 1_gt_*, 2_*_*, etc.
    # Also supports: 0_Stem, 1_Stem, 2_Method_Stem (stem may contain underscores)
    # 3-part: greedy method (.+), stem allows underscores ([A-Za-z_]+\d*)
    # 2-part: simple stem ([A-Za-z]+\d*) for names like 0_XDU743
    sota_3part = re.compile(r"^(\d+)_(.+)_([A-Za-z_]+\d*)$")
    sota_2part = re.compile(r"^(\d+)_([A-Za-z]+\d*)$")
    if any(sota_3part.match(f.stem) or sota_2part.match(f.stem) for f in images):
        return _detect_sota_flat_structure(input_dir, images, sota_3part, sota_2part)

    # Check numbered_flat pattern: 0_*, 1_*, 2_*, etc.
    numbered_pattern = re.compile(r"^(\d+)_(.+)$")
    if any(numbered_pattern.match(f.stem) for f in images):
        return _detect_numbered_flat_structure(input_dir, images, numbered_pattern)

    raise ValueError(
        f"Cannot detect directory structure in {input_dir}.\n"
        "Expected one of:\n"
        "  - Standard: Original/ and GT/ subdirectories\n"
        "  - SOTA flat: 0_yuan_*, 1_gt_*, 2_*_*.png\n"
        "  - Numbered flat: 0_*, 1_*, 2_*.png"
    )


def _detect_standard_structure(
    input_dir: Path, original_dir: Path, gt_dir: Path
) -> dict:
    """Detect standard figures/ structure with Original/, GT/, and prediction dirs."""
    originals = {}
    for f in list_images(original_dir, recursive=True):
        # Support subdirectories (e.g., Original/IRSTD-1K/file.png)
        rel = f.relative_to(original_dir)
        stem = str(rel.with_suffix(""))
        originals[stem] = f

    gt = {}
    for f in list_images(gt_dir, recursive=True):
        rel = f.relative_to(gt_dir)
        stem = str(rel.with_suffix(""))
        gt[stem] = f

    # Find prediction sources (any dir except Original and GT)
    predictions = {}
    sources = []

    for child in sorted(input_dir.iterdir()):
        if not child.is_dir() or child.name in ("Original", "GT", "__pycache__", ".git"):
            continue

        source_name = child.name
        sources.append(source_name)
        source_images = {}

        for f in list_images(child, recursive=True):
            rel = f.relative_to(child)
            stem = str(rel.with_suffix(""))
            source_images[stem] = f

        predictions[source_name] = source_images

    return {
        "type": "standard",
        "input_dir": input_dir,
        "originals": originals,
        "gt": gt,
        "predictions": predictions,
        "sources": sources,
    }


def _detect_sota_flat_structure(
    input_dir: Path, images: list[Path], pattern_3part: re.Pattern, pattern_2part: re.Pattern
) -> dict:
    """Detect SOTA flat structure.

    Rules:
      - Prefix 0 → original
      - Prefix 1 → GT
      - Everything else → prediction

    Supports two naming conventions:
      - SOTA: 0_yuan_Stem, 1_gt_Stem, 2_Model_Stem
      - Experiment: 0_Stem, 1_Stem, 2_Method_Stem
    """
    originals = {}  # stem -> path
    gt = {}         # stem -> path
    pred_groups = {}  # {model: {stem: path}}

    # Known method prefixes for original/GT (with trailing underscore)
    KNOWN_PREFIXES = {"yuan_", "gt_", "ori_", "original_"}

    # Two-pass approach:
    # Pass 1: Identify originals (prefix 0) and GTs (prefix 1) using wide pattern
    # Pass 2: For predictions, match against known stems

    wide = re.compile(r"^(\d+)_(.+)$")
    files_by_prefix = {}  # prefix -> [(clean_stem, original_stem, path)]

    for f in images:
        clean = re.sub(r"_Pred$", "", f.stem)
        m = wide.match(clean)
        if not m:
            continue
        prefix = m.group(1)
        rest = m.group(2)
        files_by_prefix.setdefault(prefix, []).append((clean, f.stem, f))

    # Pass 1: originals and GTs
    # Strip known prefixes (yuan_, gt_, etc.) if present
    for clean, orig_stem, f in files_by_prefix.get("0", []):
        m = wide.match(clean)
        rest = m.group(2)
        for pfx in KNOWN_PREFIXES:
            if rest.startswith(pfx):
                rest = rest[len(pfx):]
                break
        originals[rest] = f
    for clean, orig_stem, f in files_by_prefix.get("1", []):
        m = wide.match(clean)
        rest = m.group(2)
        for pfx in KNOWN_PREFIXES:
            if rest.startswith(pfx):
                rest = rest[len(pfx):]
                break
        gt[rest] = f

    # Collect known stems for matching predictions
    known_stems = set(originals.keys()) | set(gt.keys())

    # Pass 2: predictions (prefix >= 2)
    for prefix, entries in files_by_prefix.items():
        if prefix in ("0", "1"):
            continue
        for clean, orig_stem, f in entries:
            m = wide.match(clean)
            if not m:
                continue
            rest = m.group(2)

            # Try to match rest against known stems
            method = None
            stem = None
            for ks in known_stems:
                if rest == ks:
                    method = f"pred_{prefix}"
                    stem = ks
                    break
                elif rest.endswith(f"_{ks}"):
                    method = rest[:-(len(ks) + 1)]
                    stem = ks
                    break
                elif rest.startswith(f"{ks}_"):
                    method = rest[len(ks) + 1:]
                    stem = ks
                    break

            if stem is None:
                # No known stem match: use 3-part regex as fallback
                m3 = pattern_3part.match(clean)
                if m3:
                    method = m3.group(2)
                    stem = m3.group(3)
                else:
                    method = rest
                    stem = "unknown"

            if method not in pred_groups:
                pred_groups[method] = {}
            pred_groups[method][stem] = f

    sources = sorted(pred_groups.keys())
    predictions = pred_groups

    return {
        "type": "sota_flat",
        "input_dir": input_dir,
        "originals": originals,
        "gt": gt,
        "predictions": predictions,
        "sources": sources,
    }


def _detect_numbered_flat_structure(
    input_dir: Path, images: list[Path], pattern: re.Pattern
) -> dict:
    """Detect numbered flat structure: 0_*, 1_*, 2_*.png"""
    originals = {}  # stem -> path
    gt = {}         # stem -> path
    pred_groups = {}  # {method: {stem: path}}

    # First pass: identify stems from 0_* (originals)
    for f in images:
        m = pattern.match(f.stem)
        if not m:
            continue
        prefix = m.group(1)
        rest = m.group(2)

        if prefix == "0":
            # Extract stem: remove method prefix if exists
            # e.g., "MethodA_sample001" -> stem "sample001"
            # or just "XDU104" -> stem "XDU104"
            parts = rest.split("_", 1)
            if len(parts) > 1:
                stem = parts[1]
            else:
                stem = rest
            originals[stem] = f

    if not originals:
        raise ValueError("No original images (0_*) found in directory")

    # Second pass: match GT and predictions
    for f in images:
        m = pattern.match(f.stem)
        if not m:
            continue

        prefix = m.group(1)
        rest = m.group(2)

        if prefix == "0":
            continue  # Already processed

        if prefix == "1":
            # GT: match to stem
            for stem in originals:
                if rest == stem or rest.endswith(f"_{stem}"):
                    gt[stem] = f
                    break
            continue

        # Predictions (prefix >= 2)
        # Try to extract method and stem
        for stem in originals:
            if rest == stem:
                # Direct match (same name as original)
                method = f"pred_{prefix}"
                if method not in pred_groups:
                    pred_groups[method] = {}
                pred_groups[method][stem] = f
                break
            elif rest.endswith(f"_{stem}"):
                # Has method prefix
                method = rest[: -(len(stem) + 1)]
                if method not in pred_groups:
                    pred_groups[method] = {}
                pred_groups[method][stem] = f
                break

    sources = sorted(pred_groups.keys())

    return {
        "type": "numbered_flat",
        "input_dir": input_dir,
        "originals": originals,
        "gt": gt,
        "predictions": pred_groups,
        "sources": sources,
    }


def build_task_list(
    structure: dict,
    mode: str = "prediction",
    source: str | None = None,
    stem_filter: str | None = None,
    model_filter: str | None = None,
) -> list[dict]:
    """
    Build task list from detected structure.

    Args:
        structure: Output from detect_structure()
        mode: "prediction" or "original"
        source: Specific prediction source (for standard structure)
        stem_filter: Filter by image stem
        model_filter: Filter by model name

    Returns:
        List of task dicts with keys: stem, model, original, gt, prediction
    """
    originals = structure["originals"]
    gt = structure["gt"]
    predictions = structure["predictions"]
    sources = structure["sources"]

    # Filter sources
    if source:
        if source not in sources:
            raise ValueError(f"Source '{source}' not found. Available: {sources}")
        active_sources = [source]
    elif model_filter:
        active_sources = [s for s in sources if model_filter.lower() in s.lower()]
    else:
        active_sources = sources

    tasks = []

    if mode == "original":
        # Original mode: pair GT with Original
        for stem, gt_path in gt.items():
            if stem_filter and stem_filter not in stem:
                continue

            orig_path = originals.get(stem)
            if not orig_path:
                continue

            tasks.append({
                "stem": stem,
                "model": "original",
                "original": orig_path,
                "gt": gt_path,
                "prediction": None,
                "mode": "original",
            })
    else:
        # Prediction mode: pair GT with each prediction source
        for src in active_sources:
            pred_images = predictions.get(src, {})

            for stem, pred_path in pred_images.items():
                if stem_filter and stem_filter not in stem:
                    continue

                gt_path = gt.get(stem)
                if not gt_path:
                    continue

                orig_path = originals.get(stem)

                tasks.append({
                    "stem": stem,
                    "model": src,
                    "original": orig_path,
                    "gt": gt_path,
                    "prediction": pred_path,
                    "mode": "prediction",
                })

    tasks.sort(key=lambda t: (t["stem"], t["model"]))
    return tasks


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m cli.detector <directory>")
        sys.exit(1)

    input_path = Path(sys.argv[1])
    result = detect_structure(input_path)

    print(f"Structure type: {result['type']}")
    print(f"Input dir: {result['input_dir']}")
    print(f"Originals: {len(result['originals'])}")
    print(f"GT: {len(result['gt'])}")
    print(f"Sources: {result['sources']}")
    print(f"Predictions: {sum(len(v) for v in result['predictions'].values())}")

    tasks = build_task_list(result, mode="prediction")
    print(f"\nPrediction tasks: {len(tasks)}")
    for t in tasks[:5]:
        print(f"  {t['stem']} | {t['model']}")
    if len(tasks) > 5:
        print(f"  ... and {len(tasks) - 5} more")
