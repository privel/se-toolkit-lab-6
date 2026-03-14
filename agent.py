#!/usr/bin/env python3
"""
CLI agent with tools (read_file, list_files) and agentic loop.
Navigates the project wiki to answer questions with source references.
"""

import asyncio
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

# Load environment variables from .env.agent.secret
# override=True allows environment variables to take precedence
load_dotenv(Path(__file__).parent / ".env.agent.secret", override=True)

LLM_API_KEY = os.getenv("LLM_API_KEY")
LLM_API_BASE = os.getenv("LLM_API_BASE")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen3-coder-plus")

# Mock mode: set to True to use mock responses (no API calls)
MOCK_MODE = os.getenv("LLM_MOCK_MODE", "false").lower() == "true"

TIMEOUT_SECONDS = 60
MAX_TOOL_CALLS = 10

# Project root for file operations
PROJECT_ROOT = Path(__file__).parent


def log_debug(message: str) -> None:
    """Print debug messages to stderr."""
    print(f"[DEBUG] {message}", file=sys.stderr)


def validate_path(path: str) -> tuple[bool, str]:
    """Validate that path is safe (no traversal outside project)."""
    if not path:
        return False, "Empty path"

    # Reject absolute paths
    if Path(path).is_absolute():
        return False, "Absolute paths not allowed"

    # Reject path traversal
    if ".." in path:
        return False, "Path traversal not allowed"

    # Resolve and check it's within project root
    try:
        full_path = (PROJECT_ROOT / path).resolve()
        if not str(full_path).startswith(str(PROJECT_ROOT.resolve())):
            return False, "Path outside project root"
    except Exception as e:
        return False, f"Invalid path: {e}"

    return True, ""


def read_file(path: str) -> str:
    """Read contents of a file from the project."""
    valid, error = validate_path(path)
    if not valid:
        return f"Error: {error}"

    file_path = PROJECT_ROOT / path

    if not file_path.exists():
        return f"Error: File not found: {path}"

    if not file_path.is_file():
        return f"Error: Not a file: {path}"

    try:
        return file_path.read_text(encoding="utf-8")
    except Exception as e:
        return f"Error reading file: {e}"


def list_files(path: str) -> str:
    """List files and directories in a directory."""
    valid, error = validate_path(path)
    if not valid:
        return f"Error: {error}"

    dir_path = PROJECT_ROOT / path

    if not dir_path.exists():
        return f"Error: Directory not found: {path}"

    if not dir_path.is_dir():
        return f"Error: Not a directory: {path}"

    try:
        entries = sorted([str(e.relative_to(PROJECT_ROOT)) for e in dir_path.iterdir()])
        return "\n".join(entries)
    except Exception as e:
        return f"Error listing directory: {e}"


# Tool definitions for LLM
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file from the project repository. Use this to read file contents.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path from project root (e.g., 'wiki/git-workflow.md')",
                    }
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files and directories in a directory. Use this to discover what files exist.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative directory path from project root (e.g., 'wiki')",
                    }
                },
                "required": ["path"],
            },
        },
    },
]

SYSTEM_PROMPT = """You are a documentation assistant. You have access to tools to read files and list directories.

When answering questions:
1. Use `list_files` to discover what files exist in relevant directories (e.g., 'wiki')
2. Use `read_file` to read the contents of relevant files
3. Find the answer in the file contents
4. Include a source reference in your answer (file path + section anchor if applicable)
5. Format: "wiki/filename.md#section-anchor"

Make at most 10 tool calls. Be efficient - try to find answers with minimal tool calls.

When you have the answer, respond with a clear answer and the source reference."""


def execute_tool(name: str, args: dict[str, Any]) -> str:
    """Execute a tool and return the result."""
    log_debug(f"Executing tool: {name} with args: {args}")

    if name == "read_file":
        return read_file(args.get("path", ""))
    elif name == "list_files":
        return list_files(args.get("path", ""))
    else:
        return f"Error: Unknown tool: {name}"


def get_mock_tool_result(name: str, args: dict[str, Any]) -> str:
    """Get mock tool result for testing without real file access."""
    if name == "read_file":
        path = args.get("path", "")
        if "git-workflow" in path:
            return """# Git Workflow

## Resolving Merge Conflicts

When you have a merge conflict:

1. Open the conflicting file
2. Look for conflict markers (<<<<<<, ======, >>>>>>)
3. Edit the file to keep the desired changes
4. Stage the file: `git add <file>`
5. Commit: `git commit -m "Resolved conflict"`

## Best Practices

- Communicate with your team
- Test after resolving conflicts
- Keep commits small
"""
        return f"Contents of {path}"
    elif name == "list_files":
        path = args.get("path", "")
        if path == "wiki":
            return "git-workflow.md\nqwen.md\nllm.md\ncoding-agents.md"
        return "file1.txt\nfile2.md"
    return "Mock result"


async def call_llm_with_tools(messages: list[dict]) -> dict:
    """Call LLM with tool support and return the response."""
    if MOCK_MODE:
        log_debug("Mock mode enabled")
        # Simple mock: if last message mentions tool, return tool call
        tool_calls_count = sum(
            1 for m in messages if m.get("role") == "assistant" and m.get("tool_calls")
        )

        if tool_calls_count == 0:
            # First call: return list_files tool call
            return {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "list_files",
                            "arguments": json.dumps({"path": "wiki"}),
                        },
                    }
                ],
            }
        elif tool_calls_count == 1:
            # Second call: return read_file tool call
            return {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_2",
                        "type": "function",
                        "function": {
                            "name": "read_file",
                            "arguments": json.dumps({"path": "wiki/git-workflow.md"}),
                        },
                    }
                ],
            }
        else:
            # Third call: return final answer
            return {
                "role": "assistant",
                "content": "Edit the conflicting file, choose which changes to keep, then stage and commit. See wiki/git-workflow.md#resolving-merge-conflicts",
            }

    url = f"{LLM_API_BASE}/chat/completions"

    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": LLM_MODEL,
        "messages": messages,
        "tools": TOOLS,
        "tool_choice": "auto",
    }

    log_debug(f"Sending request to {url}")

    async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()

        data = response.json()
        return data["choices"][0]["message"]


async def run_agentic_loop(question: str) -> tuple[str, str, list[dict]]:
    """Run the agentic loop and return (answer, source, tool_calls)."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]

    tool_calls_log = []

    for iteration in range(MAX_TOOL_CALLS + 1):
        log_debug(f"Iteration {iteration + 1}")

        # Call LLM
        response = await call_llm_with_tools(messages)

        # Check for tool calls
        tool_calls = response.get("tool_calls", [])

        if not tool_calls:
            # Final answer
            answer = response.get("content", "No answer provided")

            # Extract source from answer (look for wiki/*.md# pattern)
            source = ""
            match = re.search(r"wiki/[\w-]+\.md(?:#[\w-]+)?", answer)
            if match:
                source = match.group(0)

            log_debug(f"Final answer: {answer}")
            return answer, source, tool_calls_log

        # Add assistant message with tool calls
        messages.append(response)

        # Execute each tool call
        for tool_call in tool_calls:
            func = tool_call["function"]
            tool_name = func["name"]
            tool_args = json.loads(func["arguments"])
            tool_id = tool_call["id"]

            # Execute tool
            if MOCK_MODE:
                result = get_mock_tool_result(tool_name, tool_args)
            else:
                result = execute_tool(tool_name, tool_args)

            # Log tool call
            tool_calls_log.append(
                {
                    "tool": tool_name,
                    "args": tool_args,
                    "result": result,
                }
            )

            log_debug(f"Tool {tool_name} result: {result[:100]}...")

            # Add tool result to messages
            messages.append(
                {
                    "role": "tool",
                    "content": result,
                    "tool_call_id": tool_id,
                }
            )

    # Max iterations reached
    log_debug("Max tool calls reached")
    return "Max tool calls reached without final answer", "", tool_calls_log


async def main() -> int:
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: uv run agent.py <question>", file=sys.stderr)
        return 1

    question = sys.argv[1]
    log_debug(f"Question: {question}")

    try:
        answer, source, tool_calls = await run_agentic_loop(question)

        result = {
            "answer": answer,
            "source": source,
            "tool_calls": tool_calls,
        }

        # Output only valid JSON to stdout
        print(json.dumps(result))

        return 0

    except Exception as e:
        log_debug(f"Error: {e}")
        error_result = {
            "answer": f"Error: {e}",
            "source": "",
            "tool_calls": [],
        }
        print(json.dumps(error_result))
        return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
