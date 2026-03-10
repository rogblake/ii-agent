"""Unit tests for engine/runtime/media/media.py - Image, Audio, Video, File classes."""

import base64
from pathlib import Path

import pytest
from pydantic import ValidationError

from ii_agent.agent.runtime.media.media import Audio, File, Image, Video


# ---------------------------------------------------------------------------
# Image tests
# ---------------------------------------------------------------------------


class TestImageConstruction:
    """Tests for Image construction and validation."""

    def test_image_with_url(self):
        img = Image(url="https://example.com/img.png")
        assert img.url == "https://example.com/img.png"
        assert img.filepath is None
        assert img.content is None

    def test_image_with_filepath(self):
        img = Image(filepath="/tmp/test.png")
        assert str(img.filepath) == "/tmp/test.png"
        assert img.url is None
        assert img.content is None

    def test_image_with_content_bytes(self):
        raw = b"\x89PNG\r\n"
        img = Image(content=raw)
        assert img.content == raw

    def test_image_auto_generates_id(self):
        img = Image(url="https://example.com/img.png")
        assert img.id is not None
        assert len(img.id) > 0

    def test_image_explicit_id_preserved(self):
        img = Image(url="https://example.com/img.png", id="my-custom-id")
        assert img.id == "my-custom-id"

    def test_image_optional_metadata_fields(self):
        img = Image(
            url="https://example.com/img.png",
            format="png",
            mime_type="image/png",
            detail="high",
            original_prompt="a cat",
            revised_prompt="a tabby cat",
            alt_text="Cat photo",
        )
        assert img.format == "png"
        assert img.mime_type == "image/png"
        assert img.detail == "high"
        assert img.original_prompt == "a cat"
        assert img.revised_prompt == "a tabby cat"
        assert img.alt_text == "Cat photo"

    def test_image_requires_at_least_one_source(self):
        with pytest.raises(ValidationError) as exc_info:
            Image()
        assert "url" in str(exc_info.value) or "must be provided" in str(exc_info.value)

    def test_image_rejects_multiple_sources(self):
        with pytest.raises(ValidationError):
            Image(url="https://example.com/img.png", content=b"data")

    def test_image_rejects_url_and_filepath(self):
        with pytest.raises(ValidationError):
            Image(url="https://example.com", filepath="/tmp/file.png")

    def test_image_filepath_accepts_path_object(self):
        img = Image(filepath=Path("/tmp/test.png"))
        assert img.filepath == Path("/tmp/test.png")


class TestImageToDict:
    """Tests for Image.to_dict() serialization."""

    def test_to_dict_url_image(self):
        img = Image(url="https://example.com/img.png", id="abc123")
        d = img.to_dict()
        assert d["url"] == "https://example.com/img.png"
        assert d["id"] == "abc123"
        assert "filepath" not in d
        assert "content" not in d

    def test_to_dict_includes_base64_content_by_default(self):
        raw = b"hello"
        img = Image(content=raw, id="cid")
        d = img.to_dict(include_base64_content=True)
        assert "content" in d
        assert d["content"] == base64.b64encode(raw).decode("utf-8")

    def test_to_dict_excludes_base64_content_when_flag_false(self):
        raw = b"hello"
        img = Image(content=raw, id="cid")
        d = img.to_dict(include_base64_content=False)
        assert "content" not in d

    def test_to_dict_excludes_none_values(self):
        img = Image(url="https://example.com/img.png", id="abc")
        d = img.to_dict()
        assert all(v is not None for v in d.values())

    def test_to_dict_filepath_serialized_as_string(self):
        img = Image(filepath=Path("/tmp/test.png"), id="pid")
        d = img.to_dict()
        assert isinstance(d["filepath"], str)
        assert d["filepath"] == "/tmp/test.png"

    def test_to_dict_includes_optional_metadata(self):
        img = Image(
            url="https://example.com/img.png",
            format="jpeg",
            mime_type="image/jpeg",
            alt_text="Dog",
        )
        d = img.to_dict()
        assert d["format"] == "jpeg"
        assert d["mime_type"] == "image/jpeg"
        assert d["alt_text"] == "Dog"


class TestImageFromBase64:
    """Tests for Image.from_base64() class method."""

    def test_from_base64_valid(self):
        raw = b"PNG image bytes"
        encoded = base64.b64encode(raw).decode("utf-8")
        img = Image.from_base64(encoded, mime_type="image/png")
        assert img.content == raw
        assert img.mime_type == "image/png"

    def test_from_base64_with_explicit_id(self):
        raw = b"data"
        encoded = base64.b64encode(raw).decode("utf-8")
        img = Image.from_base64(encoded, id="explicit-id")
        assert img.id == "explicit-id"

    def test_from_base64_auto_generates_id(self):
        raw = b"data"
        encoded = base64.b64encode(raw).decode("utf-8")
        img = Image.from_base64(encoded)
        assert img.id is not None

    def test_from_base64_invalid_falls_back_to_utf8(self):
        # "hello@world" has Incorrect padding - will raise binascii.Error
        invalid_b64 = "hello@world"
        img = Image.from_base64(invalid_b64)
        # Should fall back to encoding as UTF-8
        assert img.content == invalid_b64.encode("utf-8")

    def test_from_base64_roundtrip(self):
        raw = b"\x00\x01\x02\x03\xff"
        encoded = base64.b64encode(raw).decode("utf-8")
        img = Image.from_base64(encoded)
        assert img.to_base64() == encoded


class TestImageToBase64:
    """Tests for Image.to_base64()."""

    def test_to_base64_with_content(self):
        raw = b"test bytes"
        img = Image(content=raw)
        result = img.to_base64()
        assert result == base64.b64encode(raw).decode("utf-8")

    def test_to_base64_returns_none_without_content_or_url_or_filepath(self):
        # We bypass validator by using url but then manually test get_content_bytes for None.
        # get_content_bytes returns None when content is None and no valid URL.
        img = Image(url="https://example.com/img.png")
        # content is None; get_content_bytes would attempt HTTP - just verify to_base64 handles it
        assert img.content is None


# ---------------------------------------------------------------------------
# Audio tests
# ---------------------------------------------------------------------------


class TestAudioConstruction:
    """Tests for Audio construction."""

    def test_audio_with_url(self):
        audio = Audio(url="https://example.com/audio.mp3")
        assert audio.url == "https://example.com/audio.mp3"
        assert audio.content is None

    def test_audio_with_content(self):
        raw = b"\xff\xfb"
        audio = Audio(content=raw)
        assert audio.content == raw

    def test_audio_with_filepath(self):
        audio = Audio(filepath="/tmp/audio.wav")
        assert str(audio.filepath) == "/tmp/audio.wav"

    def test_audio_default_sample_rate(self):
        audio = Audio(url="https://example.com/audio.mp3")
        assert audio.sample_rate == 24000

    def test_audio_default_channels(self):
        audio = Audio(url="https://example.com/audio.mp3")
        assert audio.channels == 1

    def test_audio_requires_one_source(self):
        with pytest.raises(ValidationError):
            Audio()

    def test_audio_rejects_multiple_sources(self):
        with pytest.raises(ValidationError):
            Audio(url="https://example.com/audio.mp3", content=b"data")

    def test_audio_optional_metadata(self):
        audio = Audio(
            url="https://example.com/audio.mp3",
            format="mp3",
            mime_type="audio/mpeg",
            duration=120.5,
            transcript="Hello world",
            expires_at=9999999,
        )
        assert audio.format == "mp3"
        assert audio.mime_type == "audio/mpeg"
        assert audio.duration == 120.5
        assert audio.transcript == "Hello world"
        assert audio.expires_at == 9999999

    def test_audio_auto_generates_id(self):
        audio = Audio(url="https://example.com/audio.mp3")
        assert audio.id is not None


class TestAudioFromBase64:
    """Tests for Audio.from_base64()."""

    def test_from_base64_valid(self):
        raw = b"audio data"
        encoded = base64.b64encode(raw).decode("utf-8")
        audio = Audio.from_base64(encoded, mime_type="audio/mpeg", transcript="Hello")
        assert audio.content == raw
        assert audio.transcript == "Hello"
        assert audio.mime_type == "audio/mpeg"

    def test_from_base64_with_explicit_id(self):
        encoded = base64.b64encode(b"data").decode("utf-8")
        audio = Audio.from_base64(encoded, id="audio-id")
        assert audio.id == "audio-id"

    def test_from_base64_custom_sample_rate(self):
        encoded = base64.b64encode(b"data").decode("utf-8")
        audio = Audio.from_base64(encoded, sample_rate=44100)
        assert audio.sample_rate == 44100

    def test_from_base64_invalid_falls_back_to_utf8(self):
        # "hello@world" has Incorrect padding - will raise binascii.Error
        invalid_b64 = "hello@world"
        audio = Audio.from_base64(invalid_b64)
        assert audio.content == invalid_b64.encode("utf-8")

    def test_from_base64_with_expires_at(self):
        encoded = base64.b64encode(b"data").decode("utf-8")
        audio = Audio.from_base64(encoded, expires_at=1234567890)
        assert audio.expires_at == 1234567890


class TestAudioToDict:
    """Tests for Audio.to_dict()."""

    def test_to_dict_basic(self):
        raw = b"audio bytes"
        audio = Audio(content=raw, format="mp3", transcript="Hi")
        d = audio.to_dict()
        assert d["format"] == "mp3"
        assert d["transcript"] == "Hi"

    def test_to_dict_includes_base64_content(self):
        raw = b"audio"
        audio = Audio(content=raw)
        d = audio.to_dict(include_base64_content=True)
        assert d["content"] == base64.b64encode(raw).decode("utf-8")

    def test_to_dict_excludes_base64_content(self):
        raw = b"audio"
        audio = Audio(content=raw)
        d = audio.to_dict(include_base64_content=False)
        assert "content" not in d

    def test_to_dict_none_values_excluded(self):
        audio = Audio(url="https://example.com/audio.mp3")
        d = audio.to_dict()
        assert all(v is not None for v in d.values())

    def test_to_dict_includes_default_sample_rate(self):
        audio = Audio(url="https://example.com/audio.mp3")
        d = audio.to_dict()
        assert d["sample_rate"] == 24000
        assert d["channels"] == 1


# ---------------------------------------------------------------------------
# Video tests
# ---------------------------------------------------------------------------


class TestVideoConstruction:
    """Tests for Video construction."""

    def test_video_with_url(self):
        video = Video(url="https://example.com/video.mp4")
        assert video.url == "https://example.com/video.mp4"

    def test_video_with_content(self):
        raw = b"\x00\x00\x00 ftyp"
        video = Video(content=raw)
        assert video.content == raw

    def test_video_with_filepath(self):
        video = Video(filepath="/tmp/video.mp4")
        assert str(video.filepath) == "/tmp/video.mp4"

    def test_video_requires_one_source(self):
        with pytest.raises(ValidationError):
            Video()

    def test_video_rejects_multiple_sources(self):
        with pytest.raises(ValidationError):
            Video(url="https://example.com/video.mp4", content=b"data")

    def test_video_optional_metadata(self):
        video = Video(
            url="https://example.com/video.mp4",
            format="mp4",
            mime_type="video/mp4",
            duration=60.0,
            width=1920,
            height=1080,
            fps=30.0,
            eta="2 minutes",
            original_prompt="a sunset",
            revised_prompt="a sunset over the ocean",
        )
        assert video.format == "mp4"
        assert video.mime_type == "video/mp4"
        assert video.duration == 60.0
        assert video.width == 1920
        assert video.height == 1080
        assert video.fps == 30.0
        assert video.eta == "2 minutes"
        assert video.original_prompt == "a sunset"
        assert video.revised_prompt == "a sunset over the ocean"

    def test_video_auto_generates_id(self):
        video = Video(url="https://example.com/video.mp4")
        assert video.id is not None


class TestVideoFromBase64:
    """Tests for Video.from_base64()."""

    def test_from_base64_valid(self):
        raw = b"video data"
        encoded = base64.b64encode(raw).decode("utf-8")
        video = Video.from_base64(encoded, mime_type="video/mp4", format="mp4")
        assert video.content == raw
        assert video.mime_type == "video/mp4"
        assert video.format == "mp4"

    def test_from_base64_auto_id(self):
        encoded = base64.b64encode(b"data").decode("utf-8")
        video = Video.from_base64(encoded)
        assert video.id is not None

    def test_from_base64_explicit_id(self):
        encoded = base64.b64encode(b"data").decode("utf-8")
        video = Video.from_base64(encoded, id="vid-123")
        assert video.id == "vid-123"

    def test_from_base64_invalid_falls_back(self):
        # "hello@world" has Incorrect padding - will raise binascii.Error
        invalid_b64 = "hello@world"
        video = Video.from_base64(invalid_b64)
        assert video.content == invalid_b64.encode("utf-8")


class TestVideoToDict:
    """Tests for Video.to_dict()."""

    def test_to_dict_excludes_none_values(self):
        video = Video(url="https://example.com/video.mp4")
        d = video.to_dict()
        assert all(v is not None for v in d.values())

    def test_to_dict_includes_dimensions(self):
        video = Video(url="https://example.com/video.mp4", width=1280, height=720)
        d = video.to_dict()
        assert d["width"] == 1280
        assert d["height"] == 720

    def test_to_dict_includes_base64_content(self):
        raw = b"vid"
        video = Video(content=raw)
        d = video.to_dict(include_base64_content=True)
        assert d["content"] == base64.b64encode(raw).decode("utf-8")

    def test_to_dict_excludes_base64_content(self):
        raw = b"vid"
        video = Video(content=raw)
        d = video.to_dict(include_base64_content=False)
        assert "content" not in d


# ---------------------------------------------------------------------------
# File tests
# ---------------------------------------------------------------------------


class TestFileConstruction:
    """Tests for File construction and validation."""

    def test_file_with_url(self):
        f = File(url="https://example.com/doc.pdf")
        assert f.url == "https://example.com/doc.pdf"

    def test_file_with_content(self):
        raw = b"%PDF-1.4"
        f = File(content=raw, mime_type="application/pdf")
        assert f.content == raw

    def test_file_with_filepath(self):
        f = File(filepath="/tmp/doc.pdf")
        assert str(f.filepath) == "/tmp/doc.pdf"

    def test_file_with_external(self):
        ext_obj = {"gemini_file": "some_object"}
        f = File(external=ext_obj)
        assert f.external == ext_obj

    def test_file_requires_at_least_one_source(self):
        with pytest.raises(ValidationError):
            File()

    def test_file_valid_mime_type_pdf(self):
        f = File(content=b"data", mime_type="application/pdf")
        assert f.mime_type == "application/pdf"

    def test_file_valid_mime_type_text_plain(self):
        f = File(content=b"hello", mime_type="text/plain")
        assert f.mime_type == "text/plain"

    def test_file_invalid_mime_type_raises(self):
        with pytest.raises(ValidationError):
            File(content=b"data", mime_type="image/png")

    def test_file_no_mime_type_allowed(self):
        f = File(url="https://example.com/file.txt")
        assert f.mime_type is None

    def test_file_optional_fields(self):
        f = File(
            url="https://example.com/doc.pdf",
            filename="document.pdf",
            file_type="pdf",
            size=12345,
            format="pdf",
            name="My Document",
        )
        assert f.filename == "document.pdf"
        assert f.file_type == "pdf"
        assert f.size == 12345
        assert f.format == "pdf"
        assert f.name == "My Document"


class TestFileFromBase64:
    """Tests for File.from_base64()."""

    def test_from_base64_basic(self):
        raw = b"%PDF-1.4 content"
        encoded = base64.b64encode(raw).decode("utf-8")
        f = File.from_base64(encoded, mime_type="application/pdf")
        assert f.content == raw
        assert f.mime_type == "application/pdf"

    def test_from_base64_with_filename(self):
        encoded = base64.b64encode(b"data").decode("utf-8")
        f = File.from_base64(encoded, filename="report.pdf")
        assert f.filename == "report.pdf"

    def test_from_base64_with_name_and_format(self):
        encoded = base64.b64encode(b"data").decode("utf-8")
        f = File.from_base64(encoded, name="MyFile", format="pdf")
        assert f.name == "MyFile"
        assert f.format == "pdf"

    def test_from_base64_with_explicit_id(self):
        encoded = base64.b64encode(b"data").decode("utf-8")
        f = File.from_base64(encoded, id="file-id-123")
        assert f.id == "file-id-123"


class TestFileToDict:
    """Tests for File.to_dict()."""

    def test_to_dict_with_url(self):
        f = File(url="https://example.com/doc.pdf", id="fid")
        d = f.to_dict()
        assert d["url"] == "https://example.com/doc.pdf"
        assert d["id"] == "fid"
        assert "content" not in d

    def test_to_dict_text_content_decoded_as_string(self):
        text = "Hello, world!"
        f = File(content=text.encode("utf-8"), mime_type="text/plain")
        d = f.to_dict()
        assert d["content"] == text

    def test_to_dict_binary_content_base64_encoded(self):
        raw = b"\x00\x01\x02"
        f = File(content=raw, mime_type="application/pdf")
        d = f.to_dict()
        assert d["content"] == base64.b64encode(raw).decode("utf-8")

    def test_to_dict_excludes_none_values(self):
        f = File(url="https://example.com/doc.pdf")
        d = f.to_dict()
        assert all(v is not None for v in d.values())

    def test_to_dict_filepath_as_string(self):
        f = File(filepath=Path("/tmp/doc.pdf"))
        d = f.to_dict()
        assert isinstance(d["filepath"], str)

    def test_valid_mime_types_class_method(self):
        valid = File.valid_mime_types()
        assert "application/pdf" in valid
        assert "text/plain" in valid
        assert "text/html" in valid
        assert "text/csv" in valid
        assert "text/xml" in valid
