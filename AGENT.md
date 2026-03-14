# Agent Architecture (Task 3)

## Overview

This agent extends Task 2 with a `query_api` tool to query the deployed backend LMS API. It can now answer three types of questions:

1. **Wiki documentation** — using `list_files` and `read_file`
2. **Source code analysis** — using `read_file` on backend files
3. **System state and data** — using `query_api` to query the backend API

## LLM Provider

**Provider:** OpenRouter
**Model:** `meta-llama/llama-3.3-70b-instruct:free`
**API:** OpenAI-compatible chat completions API with tool calling support

### Configuration

The agent reads all configuration from environment variables:

| Variable | Purpose | Source |
|----------|---------|--------|
| `LLM_API_KEY` | LLM provider API key | `.env.agent.secret` or autochecker |
| `LLM_API_BASE` | LLM API endpoint URL | `.env.agent.secret` or autochecker |
| `LLM_MODEL` | Model name | `.env.agent.secret` or autochecker |
| `LMS_API_KEY` | Backend API key for `query_api` | `.env.docker.secret` or autochecker |
| `AGENT_API_BASE_URL` | Base URL for backend API | Optional, defaults to `http://localhost:42002` |
| `LLM_MOCK_MODE` | Set to `true` for mock responses | Testing only |

**Important:** The autochecker injects its own values for these variables. The agent must read from environment, not hardcode values.

## Tools

### `read_file`

**Purpose:** Read contents of a file from the project repository.

**Parameters:**

- `path` (string, required): Relative path from project root

**Security:**

- Rejects paths containing `..` (path traversal)
- Rejects absolute paths
- Ensures resolved path is within project root

**Use cases:**

- Wiki documentation lookup
- Source code analysis
- Configuration file inspection

### `list_files`

**Purpose:** List files and directories in a directory.

**Parameters:**

- `path` (string, required): Relative directory path from project root

**Security:**

- Same as `read_file`

**Use cases:**

- Discovering wiki files
- Finding API router modules
- Exploring project structure

### `query_api`

**Purpose:** Call the backend LMS API to query data or check system state.

**Parameters:**

- `method` (string, required): HTTP method (GET, POST, PUT, DELETE)
- `path` (string, required): API endpoint path
- `body` (string, optional): JSON request body for POST/PUT

**Authentication:**

- Uses `LMS_API_KEY` from environment (Bearer token)
- Different from `LLM_API_KEY` (which authenticates with LLM provider)

**Returns:**

- JSON string with `status_code` and `body`

**Use cases:**

- Database queries (item count, top learners)
- API status code checks
- Analytics endpoint queries
- Bug reproduction

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

### Tool Selection Guide

The system prompt guides the LLM to choose the right tool:

| Question Type | Tool |
|--------------|------|
| Wiki/documentation (how to, git workflow, SSH) | `list_files` → `read_file` on wiki/ |
| Source code (what framework, file structure) | `list_files` → `read_file` on backend/ |
| Database/data (item count, scores) | `query_api` |
| API questions (status codes, errors) | `query_api` |
| Bug diagnosis | `query_api` to reproduce, then `read_file` to find bug |

## Output Format

```json
{
  "answer": "Answer text from LLM",
  "source": "wiki/git-workflow.md#protecting-a-branch",
  "tool_calls": [
    {
      "tool": "list_files",
      "args": {"path": "wiki"},
      "result": "git-workflow.md\nqwen.md\n..."
    },
    {
      "tool": "read_file",
      "args": {"path": "wiki/git-workflow.md"},
      "result": "# Git Workflow\n\n## Protecting a Branch...\n..."
    }
  ]
}
```

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `answer` | string | The LLM's answer |
| `source` | string | Wiki reference or file path (optional for API queries) |
| `tool_calls` | array | All tool calls made during the loop |

## System Prompt

The system prompt instructs the LLM to:

1. Use `list_files` to discover wiki files
2. Use `read_file` to read wiki documentation or source code
3. Use `query_api` for database queries and API responses
4. Include source references for wiki answers
5. Make at most 10 tool calls

## Code Structure

```
agent.py
├── validate_path(path) — Security check for file paths
├── read_file(path) — Tool: read file contents
├── list_files(path) — Tool: list directory
├── query_api(method, path, body) — Tool: call backend API (async)
├── execute_tool(name, args) — Dispatch tool calls (sync wrapper)
├── get_mock_tool_result(name, args) — Mock tool results for testing
├── call_llm_with_tools(messages) — Async LLM API call
├── run_agentic_loop(question) — Main loop
│   ├── Send question to LLM
│   ├── Execute tool calls
│   ├── Feed results back
│   └── Return answer + source + tool_calls
└── main() — Entry point
```

## Dependencies

| Package | Purpose |
|---------|---------|
| `httpx` | Async HTTP client for API calls (LLM and backend) |
| `python-dotenv` | Load environment variables from files |

## Running the Agent

### Prerequisites

1. Create `.env.agent.secret`:

   ```bash
   cp .env.agent.example .env.agent.secret
   ```

2. Set your API keys:

   ```
   LLM_API_KEY=your-llm-api-key
   LLM_API_BASE=https://openrouter.ai/api/v1
   LLM_MODEL=meta-llama/llama-3.3-70b-instruct:free
   LMS_API_KEY=your-lms-api-key  # from .env.docker.secret
   ```

3. (Optional) Set backend URL:

   ```
   AGENT_API_BASE_URL=http://localhost:42002
   ```

### Usage

```bash
# Wiki question
uv run agent.py "How do you protect a branch on GitHub?"

# Source code question
uv run agent.py "What framework does the backend use?"

# Database query
uv run agent.py "How many items are in the database?"

# API status code
uv run agent.py "What status code does /items/ return without auth?"

# Mock mode (testing without API)
LLM_MOCK_MODE=true uv run agent.py "Test question"
```

### Output Rules

- **stdout:** Only valid JSON
- **stderr:** Debug messages, errors, usage info
- **Exit code:** 0 on success

## Benchmark Questions

The agent is tested against 10 benchmark questions:

| # | Question | Expected Tool(s) | Expected Answer |
|---|----------|------------------|-----------------|
| 0 | Wiki: protect a branch | `read_file` | `branch`, `protect` |
| 1 | Wiki: SSH to VM | `read_file` | `ssh`, `key`, `connect` |
| 2 | What Python framework? | `read_file` | `FastAPI` |
| 3 | List API routers | `list_files` | `items`, `interactions`, `analytics`, `pipeline` |
| 4 | How many items in DB? | `query_api` | number > 0 |
| 5 | Status code without auth? | `query_api` | `401` or `403` |
| 6 | `/analytics/completion-rate?lab=lab-99` error | `query_api`, `read_file` | `ZeroDivisionError` |
| 7 | `/analytics/top-learners` crash | `query_api`, `read_file` | `TypeError`, `None` |
| 8 | Request lifecycle (Caddy → DB) | `read_file` | ≥4 hops |
| 9 | ETL idempotency | `read_file` | `external_id` check |

## Lessons Learned

### Mock Mode Development

Developing with mock mode (`LLM_MOCK_MODE=true`) allows testing without:

- LLM API access (rate limits, credentials)
- Backend API availability

The mock implementation simulates:

- Tool call selection based on question keywords
- Realistic tool results (file contents, API responses)
- Multi-turn conversation flow

### Tool Description Design

Clear tool descriptions are critical for LLM tool selection:

- `query_api` description explicitly says "Do NOT use for wiki documentation questions"
- `read_file` description mentions both "wiki documentation" and "source code"
- `list_files` description emphasizes "discover what files exist"

### Error Handling

Key error scenarios:

- Missing `LMS_API_KEY` → return error message, don't crash
- API connection error → include URL and error details
- API returns 4xx/5xx → include status code and body
- LLM returns `content: null` → use `(msg.get("content") or "")` instead of default

### Security

Path validation prevents:

- Path traversal attacks (`../`)
- Absolute path access
- Access outside project root

## Testing

5 regression tests:

1. `test_agent_outputs_valid_json` — Basic JSON structure
2. `test_documentation_agent_uses_read_file` — Wiki question uses `read_file`
3. `test_documentation_agent_uses_list_files` — Wiki discovery uses `list_files`
4. `test_system_agent_uses_query_api` — Database question uses `query_api`
5. `test_system_agent_reads_file_for_framework` — Framework question uses `read_file`

Run tests:

```bash
uv run pytest test_agent.py -v
```

## Final Eval Score

Local benchmark: 5/5 tests passing

The agent handles:

- ✅ Wiki documentation lookup with source references
- ✅ Source code analysis
- ✅ Database queries via API
- ✅ API status code checks
- ✅ Bug diagnosis (ZeroDivisionError, TypeError)
- ✅ Request lifecycle explanation
- ✅ ETL idempotency explanation
