from ii_agent.agent.runtime.tools.mcp.base import MCPTool

MAX_FILE_READ_LINES = 2000
MAX_LINE_LENGTH = 2000
SUPPORTED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".heif"}
NAME = "Read"
DISPLAY_NAME = "Read file"
DESCRIPTION = f"""Reads and returns the content of a specified file from the local filesystem. Supports text files, images ({", ".join(SUPPORTED_IMAGE_EXTENSIONS)}), and PDF files.

Usage:
- file_path must be an absolute path
- Text/PDF: reads up to {MAX_FILE_READ_LINES} lines with optional offset/limit
  - Use offset and limit parameters for large files to read specific sections
  - Lines longer than {MAX_LINE_LENGTH} chars are truncated
  - Text results are returned in `cat -n` format (line numbers start at 1)
- Images: returns base64-encoded content with MIME type"""
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "file_path": {
            "type": "string",
            "description": "The absolute path to the file to read",
        },
        "limit": {
            "type": "integer",
            "description": f"Optional number of lines to read from the text file. Use for large files to limit output. Must be 1 or greater. If omitted, reads up to {MAX_FILE_READ_LINES} lines by default",
        },
        "offset": {
            "type": "integer",
            "description": "Optional line number to start reading from (1-based). Use with limit to read specific sections of large files. Must be 1 or greater. If omitted, starts from line 1",
        },
    },
    "required": ["file_path"],
}


class FileReadTool(MCPTool):
    name = NAME
    display_name = DISPLAY_NAME
    description = DESCRIPTION
    input_schema = INPUT_SCHEMA
    read_only = True
