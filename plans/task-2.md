# Task 2: The Documentation Agent - Implementation Plan

## Overview

Extend the Task 1 agent with tools (`read_file`, `list_files`) and an agentic loop to navigate the project wiki and answer questions with source references.

## LLM Provider

**Provider:** OpenRouter
**Model:** `meta-llama/llama-3.3-70b-instruct:free`
**API:** OpenAI-compatible chat completions API with tool calling support

## Tool Definitions

### `read_file`

**Purpose:** Read contents of a file from the project repository.

**Function Schema:**
```json
{
  "name": "read_file",
  "description": "Read the contents of a file from the project repository",
  "parameters": {
    "type": "object",
    "properties": {
      "path": {
        "type": "string",
        "description": "Relative path from project root (e.g., 'wiki/git-workflow.md')"
      }
    },
    "required": ["path"]
  }
}
```

**Implementation:**
- Use `Path.read_text()` to read file contents
- Security: validate path (no `..`, no absolute paths, must be within project root)
- Return error message if file doesn't exist or is not a file

### `list_files`

**Purpose:** List files and directories in a directory.

**Function Schema:**
```json
{
  "name": "list_files",
  "description": "List files and directories in a directory",
  "parameters": {
    "type": "object",
    "properties": {
      "path": {
        "type": "string",
        "description": "Relative directory path from project root (e.g., 'wiki')"
      }
    },
    "required": ["path"]
  }
}
```

**Implementation:**
- Use `Path.iterdir()` to list directory entries
- Security: same validation as `read_file`
- Return newline-separated list of relative paths

## Agentic Loop

### Algorithm

```
1. Initialize messages = [system_prompt, user_question]
2. Loop (max 10 iterations):
   a. Call LLM with messages + tool schemas
   b. If response has tool_calls:
      - Execute each tool
      - Append tool results as "tool" role messages
      - Continue loop
   c. If response has text content (no tool_calls):
      - Extract answer and source
      - Return JSON output
      - Exit
3. If max iterations reached, return partial answer
```

### Message Format

```python
messages = [
    {"role": "system", "content": SYSTEM_PROMPT},
    {"role": "user", "content": question},
    # After LLM returns tool calls:
    {"role": "assistant", "content": None, "tool_calls": [...]},
    # After executing tool:
    {"role": "tool", "content": result, "tool_call_id": "call_1"},
    # ... repeat until final answer
]
```

## System Prompt Strategy

The system prompt instructs the LLM to:
1. Use `list_files` to discover wiki files
2. Use `read_file` to read relevant file contents
3. Find the answer in the files
4. Include source reference in format: `wiki/filename.md#section-anchor`
5. Make at most 10 tool calls total

## Output Format

```json
{
  "answer": "Answer text from LLM",
  "source": "wiki/git-workflow.md#resolving-merge-conflicts",
  "tool_calls": [
    {
      "tool": "list_files",
      "args": {"path": "wiki"},
      "result": "git-workflow.md\nqwen.md\n..."
    },
    {
      "tool": "read_file",
      "args": {"path": "wiki/git-workflow.md"},
      "result": "# Git Workflow\n\n## Resolving Merge Conflicts\n..."
    }
  ]
}
```

## Security

Path validation prevents:
- Path traversal attacks (`../`)
- Absolute paths
- Access outside project root

## Testing

**Test 1:** Question about merge conflicts
- Input: "How do you resolve a merge conflict?"
- Expected: `read_file` in tool_calls, `wiki/git-workflow.md` in source

**Test 2:** Question about wiki files
- Input: "What files are in the wiki?"
- Expected: `list_files` in tool_calls with `path: "wiki"`

## Dependencies

- `httpx`: Async HTTP client for LLM API calls
- `python-dotenv`: Load environment variables from `.env.agent.secret`
