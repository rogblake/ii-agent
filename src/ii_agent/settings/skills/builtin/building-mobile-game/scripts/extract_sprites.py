#!/usr/bin/env python3
"""Split AI-generated sprite sheets into transparent PNG sprites."""

from __future__ import annotations

import argparse
from collections import deque
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Extract sprites from a sheet by removing edge-connected background, "
            "labeling connected components, and saving one PNG per component."
        )
    )
    parser.add_argument("--input", type=Path, help="Path to the source PNG sprite sheet.")
    parser.add_argument("--output-dir", type=Path, help="Directory for extracted PNG files.")
    parser.add_argument(
        "--names",
        help="Comma-separated output names without .png. Order must match sorted components.",
    )
    parser.add_argument(
        "--prefix",
        default="sprite",
        help="Fallback filename prefix when --names is omitted.",
    )
    parser.add_argument(
        "--layout",
        choices=("row", "grid"),
        default="row",
        help="Sort left-to-right for rows or top-to-bottom then left-to-right for grids.",
    )
    parser.add_argument(
        "--padding",
        type=int,
        default=4,
        help="Padding to keep around each component before final trim.",
    )
    parser.add_argument(
        "--bg-threshold",
        type=float,
        default=60.0,
        help="RGB distance threshold used when removing corner-matched background colors.",
    )
    parser.add_argument(
        "--alpha-threshold",
        type=int,
        default=20,
        help="Alpha threshold used to define foreground pixels.",
    )
    parser.add_argument(
        "--min-area",
        type=int,
        default=100,
        help="Ignore connected components smaller than this many pixels.",
    )
    parser.add_argument(
        "--dilation",
        type=int,
        default=3,
        help="Dilation radius to bridge small gaps inside a single sprite.",
    )
    parser.add_argument(
        "--normalize",
        action="store_true",
        help="Center every extracted image on the largest output canvas size.",
    )
    parser.add_argument(
        "--check-env",
        action="store_true",
        help="Validate that Pillow and numpy are importable, then exit.",
    )
    return parser.parse_args()


def import_dependencies():
    try:
        from PIL import Image
        import numpy as np
    except ModuleNotFoundError as exc:
        missing = exc.name or "required dependency"
        raise SystemExit(
            f"Missing dependency: {missing}. Install Pillow and numpy before using this script."
        ) from exc

    return Image, np


def parse_names(raw: str | None) -> list[str] | None:
    if raw is None:
        return None

    names = [part.strip() for part in raw.split(",") if part.strip()]
    if not names:
        raise SystemExit("--names was provided but no valid names were found.")
    return names


def sample_corner_colors(np, rgb):
    h, w = rgb.shape[:2]
    patch = max(1, min(h, w) // 50)

    patches = [
        rgb[:patch, :patch],
        rgb[:patch, w - patch : w],
        rgb[h - patch : h, :patch],
        rgb[h - patch : h, w - patch : w],
    ]

    return [corner.reshape(-1, 3).mean(axis=0) for corner in patches]


def walk_component(mask, start_y, start_x, visited):
    height, width = mask.shape
    queue = deque([(start_y, start_x)])
    visited[start_y, start_x] = True
    pixels = []

    while queue:
        y, x = queue.popleft()
        pixels.append((y, x))

        y_start = max(0, y - 1)
        y_stop = min(height, y + 2)
        x_start = max(0, x - 1)
        x_stop = min(width, x + 2)

        for next_y in range(y_start, y_stop):
            for next_x in range(x_start, x_stop):
                if visited[next_y, next_x] or not mask[next_y, next_x]:
                    continue
                visited[next_y, next_x] = True
                queue.append((next_y, next_x))

    return pixels


def edge_connected_mask(np, candidate_mask):
    if not candidate_mask.any():
        return candidate_mask

    height, width = candidate_mask.shape
    visited = np.zeros_like(candidate_mask, dtype=bool)
    connected = np.zeros_like(candidate_mask, dtype=bool)
    edge_points = deque()

    for x in range(width):
        if candidate_mask[0, x]:
            edge_points.append((0, x))
        if candidate_mask[height - 1, x]:
            edge_points.append((height - 1, x))

    for y in range(height):
        if candidate_mask[y, 0]:
            edge_points.append((y, 0))
        if candidate_mask[y, width - 1]:
            edge_points.append((y, width - 1))

    while edge_points:
        y, x = edge_points.popleft()
        if visited[y, x]:
            continue
        pixels = walk_component(candidate_mask, y, x, visited)
        for pixel_y, pixel_x in pixels:
            connected[pixel_y, pixel_x] = True

    return connected


def binary_dilation(np, mask, radius):
    if radius <= 0:
        return mask.copy()

    padded = np.pad(mask, radius, mode="constant", constant_values=False)
    height, width = mask.shape
    dilated = np.zeros_like(mask, dtype=bool)

    for y_offset in range(radius * 2 + 1):
        for x_offset in range(radius * 2 + 1):
            dilated |= padded[y_offset : y_offset + height, x_offset : x_offset + width]

    return dilated


def connected_components(np, mask):
    if not mask.any():
        return []

    visited = np.zeros_like(mask, dtype=bool)
    components = []

    for start_y, start_x in np.argwhere(mask):
        if visited[start_y, start_x]:
            continue

        pixels = walk_component(mask, int(start_y), int(start_x), visited)
        pixel_array = np.array(pixels, dtype=int)
        ys = pixel_array[:, 0]
        xs = pixel_array[:, 1]

        component_mask = np.zeros_like(mask, dtype=bool)
        component_mask[ys, xs] = True

        components.append(
            {
                "mask": component_mask,
                "bbox": (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())),
                "area": int(len(pixels)),
            }
        )

    return components


def remove_background(np, image_array, bg_threshold):
    rgb = image_array[:, :, :3].astype(np.float32)
    alpha = image_array[:, :, 3]

    candidates = []
    for color in sample_corner_colors(np, rgb):
        distance = np.sqrt(np.sum((rgb - color) ** 2, axis=2))
        candidates.append(distance <= bg_threshold)

    background_like = (
        np.logical_or.reduce(candidates) if candidates else np.zeros_like(alpha, dtype=bool)
    )
    background_like &= alpha > 0
    background = edge_connected_mask(np, background_like)

    near_white = np.all(rgb >= 220, axis=2) & (alpha > 0)
    near_black = np.all(rgb <= 35, axis=2) & (alpha > 0)
    border_candidate = near_white | near_black
    border_connected = edge_connected_mask(np, border_candidate)

    large_border_regions = np.zeros_like(border_connected, dtype=bool)
    for component in connected_components(np, border_connected):
        if component["area"] >= 500:
            large_border_regions |= component["mask"]

    cleaned = image_array.copy()
    cleaned[background | large_border_regions] = 0
    return cleaned


def label_components(np, image_array, alpha_threshold, dilation, min_area):
    alpha_mask = image_array[:, :, 3] > alpha_threshold
    if not alpha_mask.any():
        return []

    search_mask = binary_dilation(np, alpha_mask, dilation)
    components = []

    for component in connected_components(np, search_mask):
        component_mask = component["mask"] & alpha_mask
        area = int(component_mask.sum())
        if area < min_area:
            continue

        ys, xs = np.where(component_mask)
        components.append(
            {
                "mask": component_mask,
                "bbox": (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())),
                "area": area,
            }
        )

    return components


def sort_components(components, layout):
    if layout == "row":
        return sorted(components, key=lambda item: (item["bbox"][0], item["bbox"][1]))
    return sorted(components, key=lambda item: (item["bbox"][1], item["bbox"][0]))


def trim_image(np, image_array):
    alpha = image_array[:, :, 3] > 0
    if not alpha.any():
        return image_array

    ys, xs = np.where(alpha)
    return image_array[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]


def crop_component(np, image_array, component, padding):
    height, width = image_array.shape[:2]
    x_min, y_min, x_max, y_max = component["bbox"]

    left = max(0, x_min - padding)
    top = max(0, y_min - padding)
    right = min(width, x_max + padding + 1)
    bottom = min(height, y_max + padding + 1)

    crop = image_array[top:bottom, left:right].copy()
    crop_mask = component["mask"][top:bottom, left:right]
    crop[~crop_mask] = 0
    return trim_image(np, crop)


def normalize_crops(np, crops):
    if not crops:
        return crops

    max_height = max(crop.shape[0] for crop in crops)
    max_width = max(crop.shape[1] for crop in crops)

    normalized = []
    for crop in crops:
        canvas = np.zeros((max_height, max_width, 4), dtype=np.uint8)
        top = (max_height - crop.shape[0]) // 2
        left = (max_width - crop.shape[1]) // 2
        canvas[top : top + crop.shape[0], left : left + crop.shape[1]] = crop
        normalized.append(canvas)

    return normalized


def write_outputs(Image, output_dir, names, prefix, crops):
    output_dir.mkdir(parents=True, exist_ok=True)

    for index, crop in enumerate(crops, start=1):
        stem = names[index - 1] if names else f"{prefix}-{index:02d}"
        output_path = output_dir / f"{stem}.png"
        Image.fromarray(crop, mode="RGBA").save(output_path)
        print(output_path)


def run_extraction(args):
    Image, np = import_dependencies()

    if args.input is None or args.output_dir is None:
        raise SystemExit("--input and --output-dir are required unless --check-env is used.")

    if not args.input.exists():
        raise SystemExit(f"Input file not found: {args.input}")

    names = parse_names(args.names)

    source = Image.open(args.input).convert("RGBA")
    image_array = np.array(source)
    cleaned = remove_background(np, image_array, args.bg_threshold)
    components = label_components(
        np=np,
        image_array=cleaned,
        alpha_threshold=args.alpha_threshold,
        dilation=args.dilation,
        min_area=args.min_area,
    )
    components = sort_components(components, args.layout)

    if not components:
        raise SystemExit("No components found. Check the sprite sheet or adjust thresholds.")

    if names and len(names) != len(components):
        raise SystemExit(f"Expected {len(names)} names but found {len(components)} components.")

    crops = [crop_component(np, cleaned, component, args.padding) for component in components]
    if args.normalize:
        crops = normalize_crops(np, crops)

    write_outputs(Image, args.output_dir, names, args.prefix, crops)


def main() -> int:
    args = parse_args()

    if args.check_env:
        import_dependencies()
        print("Environment OK: Pillow and numpy are available.")
        return 0

    run_extraction(args)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130) from None
