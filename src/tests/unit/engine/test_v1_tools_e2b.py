"""Unit tests for E2B sandbox tool."""

import json
from unittest.mock import AsyncMock, MagicMock, patch, mock_open

import pytest

from ii_agent.engine.v1.tools.e2b import E2BTools


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_sandbox() -> MagicMock:
    sandbox = AsyncMock()
    sandbox.files = AsyncMock()
    sandbox.commands = AsyncMock()
    sandbox.get_host = AsyncMock(return_value="localhost:8080")
    return sandbox


def make_e2b_tools(sandbox=None) -> E2BTools:
    if sandbox is None:
        sandbox = make_sandbox()
    return E2BTools(sandbox=sandbox)


# ---------------------------------------------------------------------------
# __init__ tests
# ---------------------------------------------------------------------------

class TestE2BToolsInit:
    def test_init_sets_sandbox(self):
        sandbox = make_sandbox()
        tools = E2BTools(sandbox=sandbox)
        assert tools.sandbox is sandbox

    def test_init_last_execution_none(self):
        tools = make_e2b_tools()
        assert tools.last_execution is None

    def test_init_downloaded_files_empty(self):
        tools = make_e2b_tools()
        assert tools.downloaded_files == {}

    def test_init_has_all_tool_methods(self):
        tools = make_e2b_tools()
        # Verify key methods exist
        assert hasattr(tools, "upload_file")
        assert hasattr(tools, "download_file_from_sandbox")
        assert hasattr(tools, "run_command")
        assert hasattr(tools, "stream_command")
        assert hasattr(tools, "run_background_command")
        assert hasattr(tools, "list_files")
        assert hasattr(tools, "read_file_content")
        assert hasattr(tools, "write_file_content")
        assert hasattr(tools, "watch_directory")
        assert hasattr(tools, "get_public_url")
        assert hasattr(tools, "run_server")

    def test_toolkit_name(self):
        tools = make_e2b_tools()
        assert tools.name == "e2b_tools"


# ---------------------------------------------------------------------------
# create() classmethod tests
# ---------------------------------------------------------------------------

class TestE2BToolsCreate:
    @pytest.mark.asyncio
    async def test_create_raises_when_no_api_key(self):
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="E2B_API_KEY"):
                await E2BTools.create(api_key=None)

    @pytest.mark.asyncio
    async def test_create_uses_env_api_key(self):
        mock_sandbox = make_sandbox()
        with patch.dict("os.environ", {"E2B_API_KEY": "env-api-key"}):
            with patch("ii_agent.engine.v1.tools.e2b.AsyncSandbox") as MockSandbox:
                MockSandbox.create = AsyncMock(return_value=mock_sandbox)
                tools = await E2BTools.create()
                MockSandbox.create.assert_awaited_once()
                assert tools.sandbox is mock_sandbox

    @pytest.mark.asyncio
    async def test_create_with_explicit_api_key(self):
        mock_sandbox = make_sandbox()
        with patch("ii_agent.engine.v1.tools.e2b.AsyncSandbox") as MockSandbox:
            MockSandbox.create = AsyncMock(return_value=mock_sandbox)
            tools = await E2BTools.create(api_key="explicit-key", timeout=120)
            MockSandbox.create.assert_awaited_once_with(
                api_key="explicit-key", timeout=120
            )

    @pytest.mark.asyncio
    async def test_create_propagates_sandbox_error(self):
        with patch("ii_agent.engine.v1.tools.e2b.AsyncSandbox") as MockSandbox:
            MockSandbox.create = AsyncMock(side_effect=RuntimeError("sandbox unavailable"))
            with pytest.raises(RuntimeError, match="sandbox unavailable"):
                await E2BTools.create(api_key="key")

    @pytest.mark.asyncio
    async def test_create_with_sandbox_options(self):
        mock_sandbox = make_sandbox()
        with patch("ii_agent.engine.v1.tools.e2b.AsyncSandbox") as MockSandbox:
            MockSandbox.create = AsyncMock(return_value=mock_sandbox)
            await E2BTools.create(api_key="key", sandbox_options={"template": "custom"})
            call_kwargs = MockSandbox.create.call_args[1]
            assert call_kwargs.get("template") == "custom"


# ---------------------------------------------------------------------------
# close() tests
# ---------------------------------------------------------------------------

class TestClose:
    @pytest.mark.asyncio
    async def test_close_calls_sandbox_close(self):
        sandbox = make_sandbox()
        tools = E2BTools(sandbox=sandbox)
        await tools.close()
        sandbox.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_close_with_none_sandbox(self):
        tools = E2BTools.__new__(E2BTools)
        tools.sandbox = None
        # Should not raise
        await tools.close()


# ---------------------------------------------------------------------------
# upload_file tests
# ---------------------------------------------------------------------------

class TestUploadFile:
    @pytest.mark.asyncio
    async def test_upload_file_uses_filename_as_default_path(self):
        sandbox = make_sandbox()
        file_info = MagicMock()
        file_info.path = "/workspace/test.txt"
        sandbox.files.write = AsyncMock(return_value=file_info)
        tools = E2BTools(sandbox=sandbox)

        with patch("builtins.open", mock_open(read_data=b"content")):
            result = await tools.upload_file("/local/path/test.txt")

        assert result == "/workspace/test.txt"
        sandbox.files.write.assert_awaited_once_with("test.txt", b"content")

    @pytest.mark.asyncio
    async def test_upload_file_uses_explicit_sandbox_path(self):
        sandbox = make_sandbox()
        file_info = MagicMock()
        file_info.path = "/custom/path/test.txt"
        sandbox.files.write = AsyncMock(return_value=file_info)
        tools = E2BTools(sandbox=sandbox)

        with patch("builtins.open", mock_open(read_data=b"content")):
            result = await tools.upload_file("/local/test.txt", sandbox_path="/custom/path/test.txt")

        sandbox.files.write.assert_awaited_once_with("/custom/path/test.txt", b"content")
        assert result == "/custom/path/test.txt"

    @pytest.mark.asyncio
    async def test_upload_file_handles_exception(self):
        sandbox = make_sandbox()
        tools = E2BTools(sandbox=sandbox)

        with patch("builtins.open", side_effect=IOError("file not found")):
            result = await tools.upload_file("/nonexistent/file.txt")

        assert "error" in result.lower()


# ---------------------------------------------------------------------------
# download_file_from_sandbox tests
# ---------------------------------------------------------------------------

class TestDownloadFileFromSandbox:
    @pytest.mark.asyncio
    async def test_download_file_uses_filename_as_default_local_path(self):
        sandbox = make_sandbox()
        sandbox.files.read = AsyncMock(return_value=b"file content")
        tools = E2BTools(sandbox=sandbox)

        with patch("builtins.open", mock_open()) as mock_file:
            result = await tools.download_file_from_sandbox("/sandbox/path/file.txt")

        assert result == "file.txt"
        sandbox.files.read.assert_awaited_once_with("/sandbox/path/file.txt")

    @pytest.mark.asyncio
    async def test_download_file_handles_exception(self):
        sandbox = make_sandbox()
        sandbox.files.read = AsyncMock(side_effect=RuntimeError("read error"))
        tools = E2BTools(sandbox=sandbox)

        result = await tools.download_file_from_sandbox("/sandbox/path/file.txt")
        assert "error" in result.lower()


# ---------------------------------------------------------------------------
# run_command tests
# ---------------------------------------------------------------------------

class TestRunCommand:
    @pytest.mark.asyncio
    async def test_run_command_returns_stdout(self):
        sandbox = make_sandbox()
        cmd_result = MagicMock()
        cmd_result.stdout = "hello"
        cmd_result.stderr = None
        sandbox.commands.run = AsyncMock(return_value=cmd_result)
        tools = E2BTools(sandbox=sandbox)

        result = await tools.run_command("echo hello")
        assert "hello" in result

    @pytest.mark.asyncio
    async def test_run_command_returns_stderr(self):
        sandbox = make_sandbox()
        cmd_result = MagicMock()
        cmd_result.stdout = None
        cmd_result.stderr = "error output"
        sandbox.commands.run = AsyncMock(return_value=cmd_result)
        tools = E2BTools(sandbox=sandbox)

        result = await tools.run_command("bad_cmd")
        assert "error output" in result

    @pytest.mark.asyncio
    async def test_run_command_no_output_returns_success_message(self):
        sandbox = make_sandbox()
        cmd_result = MagicMock()
        cmd_result.stdout = None
        cmd_result.stderr = None
        sandbox.commands.run = AsyncMock(return_value=cmd_result)
        tools = E2BTools(sandbox=sandbox)

        result = await tools.run_command("touch file.txt")
        assert "no output" in result.lower() or "successfully" in result.lower()

    @pytest.mark.asyncio
    async def test_run_command_background_returns_message(self):
        sandbox = make_sandbox()
        cmd_obj = MagicMock()
        sandbox.commands.run = AsyncMock(return_value=cmd_obj)
        tools = E2BTools(sandbox=sandbox)

        result = await tools.run_command("sleep 100", background=True)
        assert "background" in result.lower()

    @pytest.mark.asyncio
    async def test_run_command_handles_exception(self):
        sandbox = make_sandbox()
        sandbox.commands.run = AsyncMock(side_effect=RuntimeError("execution failed"))
        tools = E2BTools(sandbox=sandbox)

        result = await tools.run_command("bad_cmd")
        assert "error" in result.lower()

    @pytest.mark.asyncio
    async def test_run_command_passes_callbacks(self):
        sandbox = make_sandbox()
        cmd_result = MagicMock()
        cmd_result.stdout = "output"
        cmd_result.stderr = None
        sandbox.commands.run = AsyncMock(return_value=cmd_result)
        tools = E2BTools(sandbox=sandbox)

        stdout_cb = MagicMock()
        await tools.run_command("echo hello", on_stdout=stdout_cb)
        call_kwargs = sandbox.commands.run.call_args[1]
        assert "on_stdout" in call_kwargs


# ---------------------------------------------------------------------------
# stream_command tests
# ---------------------------------------------------------------------------

class TestStreamCommand:
    @pytest.mark.asyncio
    async def test_stream_command_returns_outputs(self):
        tools = make_e2b_tools()
        with patch.object(tools, "run_command", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = "ok"
            result = await tools.stream_command("echo hello")
            mock_run.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_stream_command_handles_exception(self):
        tools = make_e2b_tools()
        with patch.object(tools, "run_command", new_callable=AsyncMock, side_effect=RuntimeError("boom")):
            result = await tools.stream_command("cmd")
            assert "error" in result.lower()


# ---------------------------------------------------------------------------
# run_background_command tests
# ---------------------------------------------------------------------------

class TestRunBackgroundCommand:
    @pytest.mark.asyncio
    async def test_run_background_command_returns_command_object(self):
        sandbox = make_sandbox()
        cmd_obj = MagicMock()
        sandbox.commands.run = AsyncMock(return_value=cmd_obj)
        tools = E2BTools(sandbox=sandbox)

        result = await tools.run_background_command("sleep 100")
        assert result is cmd_obj
        sandbox.commands.run.assert_awaited_once_with("sleep 100", background=True)

    @pytest.mark.asyncio
    async def test_run_background_command_handles_exception(self):
        sandbox = make_sandbox()
        sandbox.commands.run = AsyncMock(side_effect=RuntimeError("failed"))
        tools = E2BTools(sandbox=sandbox)

        result = await tools.run_background_command("bad_cmd")
        assert "error" in result.lower()


# ---------------------------------------------------------------------------
# list_files tests
# ---------------------------------------------------------------------------

class TestListFiles:
    @pytest.mark.asyncio
    async def test_list_files_returns_file_listing(self):
        sandbox = make_sandbox()
        file1 = MagicMock()
        file1.name = "file1.py"
        file1.type = "file"
        file1.size = 1024
        file2 = MagicMock()
        file2.name = "subdir"
        file2.type = "directory"
        file2.size = None
        sandbox.files.list = AsyncMock(return_value=[file1, file2])
        tools = E2BTools(sandbox=sandbox)

        result = await tools.list_files("/workspace")
        assert "file1.py" in result
        assert "subdir" in result
        assert "1024 bytes" in result
        assert "Directory" in result

    @pytest.mark.asyncio
    async def test_list_files_empty_directory(self):
        sandbox = make_sandbox()
        sandbox.files.list = AsyncMock(return_value=[])
        tools = E2BTools(sandbox=sandbox)

        result = await tools.list_files("/workspace")
        assert "No files found" in result

    @pytest.mark.asyncio
    async def test_list_files_handles_exception(self):
        sandbox = make_sandbox()
        sandbox.files.list = AsyncMock(side_effect=RuntimeError("permission denied"))
        tools = E2BTools(sandbox=sandbox)

        result = await tools.list_files("/workspace")
        assert "error" in result.lower()

    @pytest.mark.asyncio
    async def test_list_files_default_path_is_workspace(self):
        sandbox = make_sandbox()
        sandbox.files.list = AsyncMock(return_value=[])
        tools = E2BTools(sandbox=sandbox)

        await tools.list_files()
        sandbox.files.list.assert_awaited_once_with("/workspace")


# ---------------------------------------------------------------------------
# read_file_content tests
# ---------------------------------------------------------------------------

class TestReadFileContent:
    @pytest.mark.asyncio
    async def test_read_file_content_string_returned_as_is(self):
        sandbox = make_sandbox()
        sandbox.files.read = AsyncMock(return_value="text content")
        tools = E2BTools(sandbox=sandbox)

        result = await tools.read_file_content("/workspace/file.txt")
        assert result == "text content"

    @pytest.mark.asyncio
    async def test_read_file_content_bytes_decoded(self):
        sandbox = make_sandbox()
        sandbox.files.read = AsyncMock(return_value=b"bytes content")
        tools = E2BTools(sandbox=sandbox)

        result = await tools.read_file_content("/workspace/file.txt")
        assert result == "bytes content"

    @pytest.mark.asyncio
    async def test_read_file_content_binary_data_returns_info(self):
        sandbox = make_sandbox()
        sandbox.files.read = AsyncMock(return_value=bytes([0xFF, 0xFE, 0x00]))
        tools = E2BTools(sandbox=sandbox)

        result = await tools.read_file_content("/workspace/file.bin", encoding="utf-8")
        # Non-decodable binary should return a descriptive message
        assert "binary" in result.lower() or "bytes" in result.lower()

    @pytest.mark.asyncio
    async def test_read_file_content_handles_exception(self):
        sandbox = make_sandbox()
        sandbox.files.read = AsyncMock(side_effect=RuntimeError("not found"))
        tools = E2BTools(sandbox=sandbox)

        result = await tools.read_file_content("/workspace/missing.txt")
        assert "error" in result.lower()


# ---------------------------------------------------------------------------
# write_file_content tests
# ---------------------------------------------------------------------------

class TestWriteFileContent:
    @pytest.mark.asyncio
    async def test_write_file_content_returns_path(self):
        sandbox = make_sandbox()
        file_info = MagicMock()
        file_info.path = "/workspace/output.txt"
        sandbox.files.write = AsyncMock(return_value=file_info)
        tools = E2BTools(sandbox=sandbox)

        result = await tools.write_file_content("/workspace/output.txt", "Hello!")
        assert result == "/workspace/output.txt"
        sandbox.files.write.assert_awaited_once_with("/workspace/output.txt", b"Hello!")

    @pytest.mark.asyncio
    async def test_write_file_content_handles_exception(self):
        sandbox = make_sandbox()
        sandbox.files.write = AsyncMock(side_effect=RuntimeError("permission denied"))
        tools = E2BTools(sandbox=sandbox)

        result = await tools.write_file_content("/workspace/file.txt", "content")
        assert "error" in result.lower()


# ---------------------------------------------------------------------------
# get_public_url tests
# ---------------------------------------------------------------------------

class TestGetPublicUrl:
    @pytest.mark.asyncio
    async def test_get_public_url_returns_http_url(self):
        sandbox = make_sandbox()
        sandbox.get_host = AsyncMock(return_value="sandbox-abc.example.com")
        tools = E2BTools(sandbox=sandbox)

        result = await tools.get_public_url(8080)
        assert result == "http://sandbox-abc.example.com"
        sandbox.get_host.assert_awaited_once_with(8080)

    @pytest.mark.asyncio
    async def test_get_public_url_handles_exception(self):
        sandbox = make_sandbox()
        sandbox.get_host = AsyncMock(side_effect=RuntimeError("port not exposed"))
        tools = E2BTools(sandbox=sandbox)

        result = await tools.get_public_url(9000)
        assert "error" in result.lower()


# ---------------------------------------------------------------------------
# run_server tests
# ---------------------------------------------------------------------------

class TestRunServer:
    @pytest.mark.asyncio
    async def test_run_server_starts_command_and_returns_url(self):
        sandbox = make_sandbox()
        sandbox.commands.run = AsyncMock(return_value=MagicMock())
        sandbox.get_host = AsyncMock(return_value="sandbox-abc.example.com")
        tools = E2BTools(sandbox=sandbox)

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await tools.run_server("python server.py", 8080)

        assert result == "http://sandbox-abc.example.com"
        sandbox.commands.run.assert_awaited_once_with("python server.py", background=True)

    @pytest.mark.asyncio
    async def test_run_server_handles_exception(self):
        sandbox = make_sandbox()
        sandbox.commands.run = AsyncMock(side_effect=RuntimeError("start failed"))
        tools = E2BTools(sandbox=sandbox)

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await tools.run_server("python server.py", 8080)

        assert "error" in result.lower()
