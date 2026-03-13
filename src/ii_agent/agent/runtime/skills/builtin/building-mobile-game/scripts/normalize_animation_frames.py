#!/usr/bin/env python3
"""Normalize animation frames onto a shared canvas with one global scale."""

from __future__ import annotations

import argparse
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Normalize extracted animation frames using one global scale, a shared anchor, "
            "and an optional exact first-frame lock."
        )
    )
    parser.add_argument("--input-dir", type=Path, required=True, help="Directory containing source PNG frames.")
    parser.add_argument("--output-dir", type=Path, required=True, help="Directory for normalized PNG frames.")
    parser.add_argument("--canvas-width", type=int, default=64, help="Output frame width.")
    parser.add_argument("--canvas-height", type=int, default=64, help="Output frame height.")
    parser.add_argument("--padding", type=int, default=0, help="Minimum transparent padding inside the canvas.")
    parser.add_argument("--glob", default="*.png", help="Glob used to collect source PNG frames.")
    parser.add_argument(
        "--anchor-image",
        type=Path,
        help=(
            "Optional anchor frame. If it already matches the target canvas size, "
            "its sprite position becomes the exact shared anchor for all frames."
        ),
    )
    parser.add_argument(
        "--lock-first-frame",
        action="store_true",
        help="Copy the anchor image directly as the first output frame.",
    )
    return parser.parse_args()


def import_image():
    try:
        from PIL import Image
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "Missing dependency: Pillow. Install Pillow before using this script."
        ) from exc

    return Image


def load_rgba(Image, path: Path):
    if not path.exists():
        raise SystemExit(f"File not found: {path}")
    return Image.open(path).convert("RGBA")


def get_bbox(image):
    bbox = image.getchannel("A").getbbox()
    if bbox is None:
        raise SystemExit("Encountered a fully transparent frame; remove empty frames before normalization.")
    return bbox


def crop_to_bbox(image, bbox):
    return image.crop(bbox)


def frame_size_from_bbox(bbox):
    left, top, right, bottom = bbox
    return right - left, bottom - top


def collect_frames(input_dir: Path, pattern: str) -> list[Path]:
    frames = sorted(path for path in input_dir.glob(pattern) if path.is_file())
    if not frames:
        raise SystemExit(f"No frames matched {pattern!r} under {input_dir}")
    return frames


def compute_global_scale(
    frame_sizes,
    canvas_width: int,
    canvas_height: int,
    padding: int,
    anchor_center_x: float | None = None,
    anchor_bottom: int | None = None,
) -> float:
    usable_width = canvas_width - padding * 2
    usable_height = canvas_height - padding * 2

    if anchor_center_x is not None:
        usable_width = min(
            usable_width,
            max(1.0, (anchor_center_x - padding) * 2),
            max(1.0, (canvas_width - padding - anchor_center_x) * 2),
        )

    if anchor_bottom is not None:
        usable_height = min(usable_height, max(1, anchor_bottom - padding))

    if usable_width <= 0 or usable_height <= 0:
        raise SystemExit("Canvas size must be larger than twice the padding.")

    max_width = max(width for width, _ in frame_sizes)
    max_height = max(height for _, height in frame_sizes)

    width_scale = usable_width / max_width
    height_scale = usable_height / max_height
    return min(width_scale, height_scale)


def resize_sprite(Image, sprite, scale: float):
    width = max(1, round(sprite.width * scale))
    height = max(1, round(sprite.height * scale))
    return sprite.resize((width, height), Image.Resampling.NEAREST)


def anchor_from_exact_image(anchor_bbox):
    left, top, right, bottom = anchor_bbox
    center_x = (left + right) / 2
    return center_x, bottom


def default_anchor(canvas_width: int, canvas_height: int, padding: int):
    return canvas_width / 2, canvas_height - padding


def paste_with_anchor(Image, sprite, canvas_width: int, canvas_height: int, anchor_center_x: float, anchor_bottom: int):
    canvas = Image.new("RGBA", (canvas_width, canvas_height), (0, 0, 0, 0))
    left = round(anchor_center_x - sprite.width / 2)
    top = anchor_bottom - sprite.height

    if left < 0 or top < 0 or left + sprite.width > canvas_width or top + sprite.height > canvas_height:
        raise SystemExit(
            "A normalized frame does not fit inside the target canvas. "
            "Increase the canvas size or reduce padding."
        )

    canvas.paste(sprite, (left, top), sprite)
    return canvas


def main() -> int:
    args = parse_args()
    Image = import_image()

    frame_paths = collect_frames(args.input_dir, args.glob)
    frame_images = [load_rgba(Image, path) for path in frame_paths]
    frame_bboxes = [get_bbox(image) for image in frame_images]

    anchor_image = None
    anchor_bbox = None
    if args.anchor_image:
        anchor_image = load_rgba(Image, args.anchor_image)
        anchor_bbox = get_bbox(anchor_image)
        if args.lock_first_frame and anchor_image.size != (args.canvas_width, args.canvas_height):
            raise SystemExit(
                "--lock-first-frame requires --anchor-image to already match the target canvas size."
            )

    frame_sizes = [frame_size_from_bbox(bbox) for bbox in frame_bboxes]
    if anchor_bbox is not None:
        frame_sizes.append(frame_size_from_bbox(anchor_bbox))

    if anchor_bbox is not None and anchor_image is not None and anchor_image.size == (args.canvas_width, args.canvas_height):
        anchor_center_x, anchor_bottom = anchor_from_exact_image(anchor_bbox)
    else:
        anchor_center_x, anchor_bottom = default_anchor(
            canvas_width=args.canvas_width,
            canvas_height=args.canvas_height,
            padding=args.padding,
        )

    exact_anchor_constraints = None
    if anchor_bbox is not None and anchor_image is not None and anchor_image.size == (args.canvas_width, args.canvas_height):
        exact_anchor_constraints = (anchor_center_x, anchor_bottom)

    scale = compute_global_scale(
        frame_sizes=frame_sizes,
        canvas_width=args.canvas_width,
        canvas_height=args.canvas_height,
        padding=args.padding,
        anchor_center_x=exact_anchor_constraints[0] if exact_anchor_constraints else None,
        anchor_bottom=exact_anchor_constraints[1] if exact_anchor_constraints else None,
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)

    for index, (path, image, bbox) in enumerate(zip(frame_paths, frame_images, frame_bboxes), start=1):
        output_path = args.output_dir / path.name

        if index == 1 and args.lock_first_frame and anchor_image is not None:
            anchor_image.save(output_path)
            print(output_path)
            continue

        sprite = crop_to_bbox(image, bbox)
        resized = resize_sprite(Image, sprite, scale)
        normalized = paste_with_anchor(
            Image=Image,
            sprite=resized,
            canvas_width=args.canvas_width,
            canvas_height=args.canvas_height,
            anchor_center_x=anchor_center_x,
            anchor_bottom=anchor_bottom,
        )
        normalized.save(output_path)
        print(output_path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
