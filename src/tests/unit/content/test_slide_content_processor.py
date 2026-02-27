"""Unit tests for SlideContentProcessor pure utility methods."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from ii_agent.content.slides.content_processor import SlideContentProcessor


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_processor(url_cache=None) -> SlideContentProcessor:
    """Create a SlideContentProcessor with stub dependencies."""
    storage = MagicMock()
    sandbox = MagicMock()
    return SlideContentProcessor(storage=storage, sandbox=sandbox, url_cache=url_cache)


# ===========================================================================
# _is_external_url()
# ===========================================================================


class TestIsExternalUrl:
    """Tests for SlideContentProcessor._is_external_url()."""

    def test_http_url_is_external(self):
        proc = _make_processor()
        assert proc._is_external_url("http://example.com/image.png") is True

    def test_https_url_is_external(self):
        proc = _make_processor()
        assert proc._is_external_url("https://cdn.example.com/photo.jpg") is True

    def test_data_uri_is_external(self):
        proc = _make_processor()
        assert proc._is_external_url("data:image/png;base64,AAAA") is True

    def test_protocol_relative_url_is_external(self):
        proc = _make_processor()
        assert proc._is_external_url("//cdn.example.com/asset.js") is True

    def test_mailto_is_external(self):
        proc = _make_processor()
        assert proc._is_external_url("mailto:user@example.com") is True

    def test_tel_is_external(self):
        proc = _make_processor()
        assert proc._is_external_url("tel:+1234567890") is True

    def test_fragment_link_is_external(self):
        proc = _make_processor()
        assert proc._is_external_url("#section-1") is True

    def test_relative_path_is_not_external(self):
        proc = _make_processor()
        assert proc._is_external_url("images/photo.png") is False

    def test_absolute_local_path_is_not_external(self):
        proc = _make_processor()
        assert proc._is_external_url("/home/user/slides/image.png") is False

    def test_relative_parent_path_is_not_external(self):
        proc = _make_processor()
        assert proc._is_external_url("../assets/logo.svg") is False

    def test_filename_only_is_not_external(self):
        proc = _make_processor()
        assert proc._is_external_url("background.jpg") is False

    def test_empty_string_is_not_external(self):
        proc = _make_processor()
        assert proc._is_external_url("") is False

    def test_ftp_url_is_not_external(self):
        # Only http, https, data, //, mailto, tel and # are treated as external.
        proc = _make_processor()
        # ftp does NOT match any of those prefixes.
        assert proc._is_external_url("ftp://files.example.com/file.zip") is False

    def test_http_without_slashes_is_not_external(self):
        proc = _make_processor()
        # "http" prefix but only "http:" without "http://" – still starts with "http://"? No.
        # "http:somefile" starts with "http:" which is not in the startswith tuple as a standalone.
        # Let's verify: "http:somefile".startswith(("http://", "https://", ...)) is False.
        assert proc._is_external_url("http:somefile") is False


# ===========================================================================
# _resolve_sandbox_file_path()
# ===========================================================================


class TestResolveSandboxFilePath:
    """Tests for SlideContentProcessor._resolve_sandbox_file_path()."""

    def test_absolute_path_returned_as_is(self):
        proc = _make_processor()
        result = proc._resolve_sandbox_file_path(
            "/var/slides/image.png",
            "/home/user/presentation.html",
        )
        assert result == "/var/slides/image.png"

    def test_relative_path_resolved_against_slide_dir(self):
        proc = _make_processor()
        result = proc._resolve_sandbox_file_path(
            "images/photo.png",
            "/home/user/slides/presentation.html",
        )
        assert result == "/home/user/slides/images/photo.png"

    def test_relative_path_with_parent_traversal_normalized(self):
        proc = _make_processor()
        result = proc._resolve_sandbox_file_path(
            "../assets/logo.svg",
            "/home/user/slides/presentation.html",
        )
        assert result == "/home/user/assets/logo.svg"

    def test_current_directory_relative_path(self):
        proc = _make_processor()
        result = proc._resolve_sandbox_file_path(
            "./background.jpg",
            "/home/user/slides/deck.html",
        )
        assert result == "/home/user/slides/background.jpg"

    def test_returns_none_when_exception_occurs(self):
        proc = _make_processor()
        # Pass a non-string to provoke an internal exception.
        result = proc._resolve_sandbox_file_path(None, "/some/path.html")  # type: ignore[arg-type]
        assert result is None

    def test_slide_in_root_directory(self):
        proc = _make_processor()
        result = proc._resolve_sandbox_file_path(
            "img.png",
            "/presentation.html",
        )
        assert result == "/img.png"

    def test_absolute_path_not_affected_by_slide_location(self):
        proc = _make_processor()
        result = proc._resolve_sandbox_file_path(
            "/absolute/resource.css",
            "/completely/different/path/slide.html",
        )
        assert result == "/absolute/resource.css"

    def test_deeply_nested_relative_path(self):
        proc = _make_processor()
        result = proc._resolve_sandbox_file_path(
            "a/b/c/image.png",
            "/home/user/deck.html",
        )
        assert result == "/home/user/a/b/c/image.png"

    def test_multiple_parent_traversals(self):
        proc = _make_processor()
        result = proc._resolve_sandbox_file_path(
            "../../shared/style.css",
            "/home/user/slides/advanced/presentation.html",
        )
        assert result == "/home/user/shared/style.css"


# ===========================================================================
# _generate_storage_path_from_content()
# ===========================================================================


class TestGenerateStoragePathFromContent:
    """Tests for SlideContentProcessor._generate_storage_path_from_content()."""

    def test_path_starts_with_slides_assets(self):
        proc = _make_processor()
        result = proc._generate_storage_path_from_content(
            "abc123def456", Path("/home/user/image.png")
        )
        assert result.startswith("slides/assets/")

    def test_path_includes_content_hash(self):
        proc = _make_processor()
        content_hash = "deadbeef1234567890abcdef12345678"
        result = proc._generate_storage_path_from_content(
            content_hash, Path("/tmp/image.png")
        )
        assert content_hash in result

    def test_path_includes_file_extension(self):
        proc = _make_processor()
        result = proc._generate_storage_path_from_content(
            "hash123", Path("/tmp/photo.jpg")
        )
        assert result.endswith(".jpg")

    def test_png_extension_preserved(self):
        proc = _make_processor()
        result = proc._generate_storage_path_from_content(
            "hash123", Path("/tmp/image.png")
        )
        assert result.endswith(".png")

    def test_svg_extension_preserved(self):
        proc = _make_processor()
        result = proc._generate_storage_path_from_content(
            "hash123", Path("/tmp/icon.svg")
        )
        assert result.endswith(".svg")

    def test_no_extension_produces_no_dot_suffix(self):
        proc = _make_processor()
        result = proc._generate_storage_path_from_content(
            "hash123", Path("/tmp/file_without_extension")
        )
        # When there's no extension the result should end with the hash (no trailing dot).
        assert result == "slides/assets/hash123"

    def test_returns_string(self):
        proc = _make_processor()
        result = proc._generate_storage_path_from_content("h", Path("/f.txt"))
        assert isinstance(result, str)

    def test_different_hashes_produce_different_paths(self):
        proc = _make_processor()
        path = Path("/tmp/image.png")
        result_a = proc._generate_storage_path_from_content("hash_aaa", path)
        result_b = proc._generate_storage_path_from_content("hash_bbb", path)
        assert result_a != result_b

    def test_same_hash_same_name_always_same_path(self):
        proc = _make_processor()
        path = Path("/tmp/image.png")
        result_1 = proc._generate_storage_path_from_content("fixed_hash", path)
        result_2 = proc._generate_storage_path_from_content("fixed_hash", path)
        assert result_1 == result_2

    def test_full_path_format(self):
        proc = _make_processor()
        content_hash = "abc"
        result = proc._generate_storage_path_from_content(content_hash, Path("style.css"))
        assert result == "slides/assets/abc.css"

    def test_uppercase_extension_preserved(self):
        proc = _make_processor()
        result = proc._generate_storage_path_from_content(
            "hash123", Path("/tmp/IMAGE.PNG")
        )
        assert result.endswith(".PNG")


# ===========================================================================
# Constructor / initialization
# ===========================================================================


class TestSlideContentProcessorInit:
    """Tests for SlideContentProcessor initialization."""

    def test_default_url_cache_is_empty_dict(self):
        storage = MagicMock()
        sandbox = MagicMock()
        proc = SlideContentProcessor(storage=storage, sandbox=sandbox)
        assert proc.url_cache == {}

    def test_provided_url_cache_is_used(self):
        storage = MagicMock()
        sandbox = MagicMock()
        cache = {"hash1": "https://example.com/1.png"}
        proc = SlideContentProcessor(storage=storage, sandbox=sandbox, url_cache=cache)
        assert proc.url_cache is cache

    def test_storage_attribute_set(self):
        storage = MagicMock()
        sandbox = MagicMock()
        proc = SlideContentProcessor(storage=storage, sandbox=sandbox)
        assert proc.storage is storage

    def test_sandbox_attribute_set(self):
        storage = MagicMock()
        sandbox = MagicMock()
        proc = SlideContentProcessor(storage=storage, sandbox=sandbox)
        assert proc.sandbox is sandbox
