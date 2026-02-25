from pathlib import Path

import pytest

from ii_agent.content.media.utils import load_yaml_config


def test_load_yaml_config_raises_for_missing_file(tmp_path):
    missing_path = tmp_path / "missing.yml"

    with pytest.raises(FileNotFoundError):
        load_yaml_config(missing_path)


def test_load_yaml_config_reads_yaml_content(tmp_path):
    config_path = tmp_path / "config.yml"
    config_path.write_text("name: media\nenabled: true\ncount: 3\n", encoding="utf-8")

    loaded = load_yaml_config(Path(config_path))

    assert loaded == {"name": "media", "enabled": True, "count": 3}
