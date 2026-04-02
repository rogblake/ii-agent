"""Constants for media domain."""

from pathlib import Path

IMAGE_MINI_TOOLS_TYPE = "image-mini-tools"

# YAML config directory for media model definitions (video/image)
CONFIG_DIR = Path(__file__).parent / "config"
VIDEO_CONFIG_PATH = CONFIG_DIR / "video.yaml"
IMAGE_CONFIG_PATH = CONFIG_DIR / "image.yaml"
