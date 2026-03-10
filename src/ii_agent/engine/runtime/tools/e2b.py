import asyncio
import json
from os import getenv
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from e2b_code_interpreter import AsyncSandbox

from ii_agent.engine.runtime.tools.toolkit import Toolkit
from ii_agent.core.logger import logger

class E2BTools(Toolkit):
    def __init__(
        self,
        sandbox: AsyncSandbox,
        **kwargs,
    ):
        """Initialize E2B toolkit for code interpretation and running Python code in a sandbox.

        Note: Use E2BTools.create() class method to instantiate this class properly.

        Args:
            sandbox: An initialized AsyncSandbox instance
        """
        self.sandbox = sandbox

        # Last execution result for reference
        self.last_execution = None
        self.downloaded_files: Dict[int, str] = {}

        tools: List[Any] = [
            self.upload_file,
            self.download_file_from_sandbox,
            # Filesystem operations
            self.list_files,
            self.read_file_content,
            self.write_file_content,
            self.watch_directory,
            # Internet access
            self.get_public_url,
            self.run_server,
            # Command execution
            self.run_command,
            self.stream_command,
            self.run_background_command,
        ]

        super().__init__(name="e2b_tools", tools=tools, **kwargs)

    @classmethod
    async def create(
        cls,
        api_key: Optional[str] = None,
        timeout: int = 300,  # 5 minutes default timeout
        sandbox_options: Optional[Dict[str, Any]] = None,
        **kwargs,
    ):
        """Create and initialize an E2BTools instance with an async sandbox.

        Args:
            api_key: E2B API key (defaults to E2B_API_KEY environment variable)
            timeout: Timeout in seconds for the sandbox (default: 5 minutes)
            sandbox_options: Additional options to pass to the AsyncSandbox constructor
            **kwargs: Additional arguments to pass to Toolkit

        Returns:
            E2BTools: Initialized E2BTools instance

        Raises:
            ValueError: If E2B_API_KEY is not set
        """
        api_key = api_key or getenv("E2B_API_KEY")
        if not api_key:
            raise ValueError(
                "E2B_API_KEY not set. Please set the E2B_API_KEY environment variable."
            )

        sandbox_options = sandbox_options or {}

        try:
            sandbox = await AsyncSandbox.create(api_key=api_key, timeout=timeout, **sandbox_options)
        except Exception as e:
            logger.error(f"Could not create sandbox: {e}")
            raise e

        return cls(sandbox=sandbox, **kwargs)

    async def close(self):
        """Close the sandbox and clean up resources."""
        if self.sandbox:
            await self.sandbox.close()

    # File Upload/Download Functions
    async def upload_file(self, file_path: str, sandbox_path: Optional[str] = None) -> str:
        """
        Upload a file to the E2B sandbox.

        Args:
            file_path (str): Path to the file on the local system
            sandbox_path (str, optional): Destination path in the sandbox. Defaults to the same filename.

        Returns:
            str: Path to the file in the sandbox or error message
        """
        try:
            # Determine the sandbox path if not provided
            if not sandbox_path:
                sandbox_path = Path(file_path).name

            # Upload the file
            with open(file_path, "rb") as f:
                file_content = f.read()
                file_in_sandbox = await self.sandbox.files.write(sandbox_path, file_content)

            return file_in_sandbox.path
        except Exception as e:
            return json.dumps({"status": "error", "message": f"Error uploading file: {str(e)}"})

    async def download_file_from_sandbox(
        self, sandbox_path: str, local_path: Optional[str] = None
    ) -> str:
        """
        Download a file from the E2B sandbox to the local system.

        Args:
            sandbox_path (str): Path to the file in the sandbox
            local_path (str, optional): Destination path on the local system. Defaults to the same filename.

        Returns:
            str: Path to the downloaded file or error message
        """
        try:
            # Determine local path if not provided
            if not local_path:
                local_path = Path(sandbox_path).name

            # Download the file
            content = await self.sandbox.files.read(sandbox_path)

            with open(local_path, "wb") as f:
                f.write(content)

            return local_path
        except Exception as e:
            return json.dumps({"status": "error", "message": f"Error downloading file: {str(e)}"})

    # Command Execution Functions
    async def run_command(
        self,
        command: str,
        on_stdout: Optional[Callable] = None,
        on_stderr: Optional[Callable] = None,
        background: bool = False,
    ) -> str:
        """
        Run a shell command in the sandbox environment.

        Args:
            command (str): Shell command to execute
            on_stdout (callable, optional): Callback function for streaming stdout
            on_stderr (callable, optional): Callback function for streaming stderr
            background (bool): Whether to run the command in background

        Returns:
            str: Command results or error message, or the command object for background execution
        """
        try:
            # Prepare streaming callbacks
            kwargs = {}
            if on_stdout:
                kwargs["on_stdout"] = on_stdout
            if on_stderr:
                kwargs["on_stderr"] = on_stderr

            # Set background execution if requested
            process_kwargs = {
                "background": background
            }  # Using a separate dict for process arguments

            # Execute the command
            result = await self.sandbox.commands.run(command, **kwargs, **process_kwargs)

            # For background execution, return the command object
            if background:
                return "Command started in background. Use the returned command object to interact with it."

            # For synchronous execution, return the output
            output = []
            if hasattr(result, "stdout") and result.stdout:
                output.append(f"STDOUT:\n{result.stdout}")
            if hasattr(result, "stderr") and result.stderr:
                output.append(f"STDERR:\n{result.stderr}")

            return json.dumps(output) if output else "Command executed successfully with no output."

        except Exception as e:
            return json.dumps({"status": "error", "message": f"Error executing command: {str(e)}"})

    async def stream_command(self, command: str) -> str:
        """
        Run a shell command and stream its output.

        Args:
            command (str): Shell command to execute

        Returns:
            str: Summary of command execution
        """
        outputs = []

        def stdout_callback(data):
            outputs.append(f"STDOUT: {data}")
            logger.info(f"STDOUT: {data}")

        def stderr_callback(data):
            outputs.append(f"STDERR: {data}")
            logger.error(f"STDERR: {data}")

        try:
            await self.run_command(command, on_stdout=stdout_callback, on_stderr=stderr_callback)
            return json.dumps(outputs) if outputs else "Command completed with no output."
        except Exception as e:
            return json.dumps({"status": "error", "message": f"Error streaming command: {str(e)}"})

    async def run_background_command(self, command: str) -> Any:
        """
        Run a shell command in the background.

        Args:
            command (str): Shell command to execute in background

        Returns:
            object: Command object that can be used to interact with the background process
        """
        try:
            # Execute the command in background
            command_obj = await self.sandbox.commands.run(command, background=True)
            return command_obj
        except Exception as e:
            return json.dumps(
                {
                    "status": "error",
                    "message": f"Error starting background command: {str(e)}",
                }
            )

    # Filesystem Operations
    async def list_files(self, directory_path: str = "/workspace") -> str:
        """
        List files and directories in the specified path in the sandbox.

        Args:
            directory_path (str): Path to the directory to list (default: /workspace directory)

        Returns:
            str: List of files and directories or error message
        """
        try:
            files = await self.sandbox.files.list(directory_path)
            if not files:
                return f"No files found in {directory_path}"

            result = f"Contents of {directory_path}:\n"
            for file in files:
                file_type = "Directory" if file.type == "directory" else "File"
                size = f"{file.size} bytes" if file.size is not None else "Unknown size"
                result += f"- {file.name} ({file_type}, {size})\n"

            return result
        except Exception as e:
            return json.dumps({"status": "error", "message": f"Error listing files: {str(e)}"})

    async def read_file_content(self, file_path: str, encoding: str = "utf-8") -> str:
        """
        Read the content of a file from the sandbox.

        Args:
            file_path (str): Path to the file in the sandbox
            encoding (str): Encoding to use for text files (default: utf-8)

        Returns:
            str: File content or error message
        """
        try:
            content = await self.sandbox.files.read(file_path)

            # Check if content is already a string or if it's bytes that need decoding
            if isinstance(content, str):
                return content
            elif isinstance(content, bytes):
                # Try to decode as text if encoding is provided
                try:
                    text_content = content.decode(encoding)
                    return text_content
                except UnicodeDecodeError:
                    return f"File read successfully but contains binary data ({len(content)} bytes). Use download_file_from_sandbox to save it."
            else:
                # Handle unexpected content type
                return f"Unexpected content type: {type(content)}. Expected str or bytes."

        except Exception as e:
            return json.dumps({"status": "error", "message": f"Error reading file: {str(e)}"})

    async def write_file_content(self, file_path: str, content: str) -> str:
        """
        Write text content to a file in the sandbox.

        Args:
            file_path (str): Path to the file in the sandbox
            content (str): Text content to write

        Returns:
            str: Success message or error message
        """
        try:
            # Convert string to bytes
            bytes_content = content.encode("utf-8")

            # Write the file
            file_info = await self.sandbox.files.write(file_path, bytes_content)

            return file_info.path
        except Exception as e:
            return json.dumps({"status": "error", "message": f"Error writing file: {str(e)}"})

    async def watch_directory(self, directory_path: str, duration_seconds: int = 5) -> str:
        """
        Watch a directory for changes for a specified duration.

        Args:
            directory_path (str): Path to the directory to watch
            duration_seconds (int): How long to watch for changes in seconds (default: 5 seconds)

        Returns:
            str: List of changes detected or error message
        """
        try:
            changes = []

            # Setup watcher
            watcher = await self.sandbox.files.watch_dir(directory_path)

            # Watch for changes
            start_time = asyncio.get_event_loop().time()
            while asyncio.get_event_loop().time() - start_time < duration_seconds:
                try:
                    # Get change with timeout
                    change = await asyncio.wait_for(watcher.get_change(), timeout=0.5)
                    if change:
                        changes.append(f"{change.event} - {change.path}")
                except asyncio.TimeoutError:
                    # No change detected in this interval, continue watching
                    continue

            # Close watcher
            await watcher.close()

            if changes:
                return json.dumps(
                    {
                        "status": "success",
                        "message": f"Changes detected in {directory_path} over {duration_seconds} seconds:\n"
                        + "\n".join(changes),
                    }
                )
            else:
                return json.dumps(
                    {
                        "status": "success",
                        "message": f"No changes detected in {directory_path} over {duration_seconds} seconds",
                    }
                )

        except Exception as e:
            return json.dumps({"status": "error", "message": f"Error watching directory: {str(e)}"})

    # Internet Access Functions
    async def get_public_url(self, port: int) -> str:
        """
        Get a public URL for a service running in the sandbox on the specified port.

        Args:
            port (int): Port number the service is running on in the sandbox

        Returns:
            str: Public URL or error message
        """
        try:
            host = await self.sandbox.get_host(port)

            return f"http://{host}"
        except Exception as e:
            return json.dumps({"status": "error", "message": f"Error getting public URL: {str(e)}"})

    async def run_server(self, command: str, port: int) -> str:
        """
        Start a server in the sandbox and return its public URL.

        Args:
            command (str): Command to start the server
            port (int): Port the server will listen on

        Returns:
            str: Server information including public URL or error message
        """
        try:
            # Start the server in the background
            await self.sandbox.commands.run(command, background=True)

            # Wait a moment for the server to start
            await asyncio.sleep(2)

            # Get the public URL
            host = await self.sandbox.get_host(port)
            url = f"http://{host}"

            return url
        except Exception as e:
            return json.dumps({"status": "error", "message": f"Error starting server: {str(e)}"})
