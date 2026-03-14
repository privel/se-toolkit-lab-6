# Task 3: The System Agent - Implementation Plan

## Overview

Extend the Task 2 agent with a `query_api` tool to query the deployed backend API. This enables the agent to answer questions about the actual system state (database contents, API responses) in addition to wiki documentation.

## New Tool: `query_api`

### Function Schema

```json
{
  "name": "query_api",
  "description": "Call the backend LMS API to query data or perform operations. Use this for questions about database contents, API responses, or system state.",
  "parameters": {
    "type": "object",
    "properties": {
      "method": {
        "type": "string",
        "description": "HTTP method (GET, POST, PUT, DELETE)"
      },
      "path": {
        "type": "string",
        "description": "API endpoint path (e.g., '/items/', '/analytics/completion-rate')"
      },
      "body": {
        "type": "string",
        "description": "Optional JSON request body for POST/PUT requests"
      }
    },
    "required": ["method", "path"]
  }
}
```

### Implementation

```python
def query_api(method: str, path: str, body: Optional[str] = None) -> str:
    """Call the backend API and return response."""
    base_url = os.getenv("AGENT_API_BASE_URL", "http://localhost:42002")
    lms_api_key = os.getenv("LMS_API_KEY")
    
    url = f"{base_url}{path}"
    headers = {
        "Authorization": f"Bearer {lms_api_key}",
        "Content-Type": "application/json",
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.request(method, url, headers=headers, json=body)
        return json.dumps({
            "status_code": response.status_code,
            "body": response.json() if response.content else response.text
        })
```

### Authentication

- Uses `LMS_API_KEY` from `.env.docker.secret` (not `LLM_API_KEY`)
- Two distinct keys:
  - `LLM_API_KEY` → authenticates with LLM provider
  - `LMS_API_KEY` → authenticates with backend LMS API

## Environment Variables

| Variable | Purpose | Source | Default |
|----------|---------|--------|---------|
| `LLM_API_KEY` | LLM provider API key | `.env.agent.secret` | - |
| `LLM_API_BASE` | LLM API endpoint URL | `.env.agent.secret` | - |
| `LLM_MODEL` | Model name | `.env.agent.secret` | `qwen3-coder-plus` |
| `LMS_API_KEY` | Backend API key for `query_api` | `.env.docker.secret` | - |
| `AGENT_API_BASE_URL` | Base URL for `query_api` | Optional | `http://localhost:42002` |

**Important:** The autochecker injects its own values for these variables. The agent must read from environment, not hardcode.

## System Prompt Updates

The system prompt should guide the LLM to choose the right tool:

1. **Wiki questions** (documentation, how-to) → `list_files`, `read_file`
2. **System facts** (framework, ports, status codes) → `query_api`
3. **Data queries** (item count, scores) → `query_api`
4. **Bug diagnosis** (API errors) → `query_api` + `read_file`

### Updated System Prompt

```
You are a documentation and system assistant. You have access to tools:

1. `list_files` - List files in a directory (use for discovering wiki files)
2. `read_file` - Read file contents (use for wiki documentation and source code)
3. `query_api` - Call the backend API (use for database queries, API responses, system state)

When answering questions:
- For wiki/documentation questions: use `list_files` and `read_file`
- For system/data questions: use `query_api`
- For bug diagnosis: use `query_api` to reproduce the error, then `read_file` to find the bug

Include source references for wiki answers (e.g., `wiki/git-workflow.md#section`).
For API answers, include the endpoint path.

Make at most 10 tool calls total.
```

## Agentic Loop

No changes to the loop structure — just add `query_api` to the tool schemas:

```python
TOOLS = [
    {...},  # read_file
    {...},  # list_files
    {...},  # query_api (new)
]
```

## Output Format

```json
{
  "answer": "There are 120 items in the database.",
  "source": "",  # Optional for API queries
  "tool_calls": [
    {
      "tool": "query_api",
      "args": {"method": "GET", "path": "/items/"},
      "result": "{\"status_code\": 200, \"body\": [...]}"
    }
  ]
}
```

## Benchmark Questions

| # | Question | Expected Tool | Expected Answer |
|---|----------|---------------|-----------------|
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

## Testing

**Test 1:** Framework question
- Input: "What framework does the backend use?"
- Expected: `read_file` in tool_calls, answer contains "FastAPI"

**Test 2:** Database query
- Input: "How many items are in the database?"
- Expected: `query_api` in tool_calls, answer contains a number

## Error Handling

| Error | Handling |
|-------|----------|
| Missing `LMS_API_KEY` | Return error: "LMS_API_KEY not configured" |
| API connection error | Return error message in result |
| API returns 4xx/5xx | Include status code and error body |
| Timeout | httpx timeout, log to stderr |

## Iteration Strategy

1. Add `query_api` tool
2. Run `uv run run_eval.py`
3. For each failure:
   - Check if wrong tool was called → improve system prompt
   - Check if tool returned error → fix implementation
   - Check if answer phrasing wrong → adjust prompt
4. Re-run until all 10 pass
