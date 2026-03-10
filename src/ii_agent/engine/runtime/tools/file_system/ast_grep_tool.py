from ii_agent.engine.runtime.tools.mcp.base import MCPTool

NAME = "ASTGrep"
DISPLAY_NAME = "AST-based code search"
DESCRIPTION = """Searches for AST patterns within code files using structural matching. Supports multiple programming languages and returns matches with file paths, line numbers, and code context.
YOU MUST USE THIS TOOL WHENEVER YOU WANT TO SEARCH FOR CODE.
Usage:
- AST patterns: Use code-like patterns with wildcards (e.g., 'function $NAME($ARGS) { $BODY }', 'import $MODULE from "$PATH"')
- Wildcards: Use $UPPERCASE for capturing parts (e.g., $NAME, $ARGS, $BODY)
- Language auto-detection: Automatically detects programming language from file extensions
- Filter files by pattern with the `include` parameter (e.g., '*.js', '*.{ts,tsx}')
- Supports 20+ programming languages including JavaScript, TypeScript, Python, Java, Go, Rust, etc.
"""
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "pattern": {
            "type": "string",
            "description": "AST pattern to search for (e.g., 'function $NAME($ARGS) { $BODY }', 'class $CLASS extends $PARENT', 'import $MODULE from \"$PATH\"')",
        },
        "path": {
            "type": "string",
            "description": "The absolute path to the directory to search within. If omitted, searches the current working directory",
        },
        "include": {
            "type": "string",
            "description": "A glob pattern to filter which files are searched (e.g., '*.js', '*.{ts,tsx}', 'src/**'). If omitted, searches all files",
        },
        "language": {
            "type": "string",
            "description": "Programming language for AST parsing (e.g., 'javascript', 'python', 'typescript'). If omitted, auto-detects from file extensions",
        },
    },
    "required": ["pattern"],
}


class ASTGrepTool(MCPTool):
    name = NAME
    display_name = DISPLAY_NAME
    description = DESCRIPTION
    input_schema = INPUT_SCHEMA
    read_only = True
