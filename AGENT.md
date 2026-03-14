# Agent Architecture

## Overview

This agent is a CLI tool that sends questions to an LLM and returns structured JSON answers. It is the foundation for the agentic system that will be extended with tools in Tasks 2–3.

## LLM Provider

**Provider:** OpenRouter
**Model:** `meta-llama/llama-3.3-70b-instruct:free`
**API:** OpenAI-compatible chat completions API

### Configuration

The agent reads configuration from `.env.agent.secret`:

| Variable | Description |
|----------|-------------|
| `LLM_API_KEY` | OpenRouter API key |
| `LLM_API_BASE` | API base URL (`https://openrouter.ai/api/v1`) |
| `LLM_MODEL` | Model name (`meta-llama/llama-3.3-70b-instruct:free`) |
| `LLM_MOCK_MODE` | Set to `true` for mock responses (testing without API) |

## How It Works

### Input/Output

**Input:**

```bash
uv run agent.py "What does REST stand for?"
```

**Output:**

```json
{"answer": "Representational State Transfer.", "tool_calls": []}
```

### Flow

1. **Parse arguments** — Read question from `sys.argv[1]`
2. **Load config** — Load `.env.agent.secret` with `python-dotenv`
3. **Call LLM** — Async POST to `/chat/completions` via `httpx`
4. **Format response** — Extract answer, add empty `tool_calls`
5. **Output JSON** — Print to stdout (debug to stderr)

### Code Structure

```
agent.py
├── load_dotenv() — Load .env.agent.secret
├── call_llm(question) — Async LLM API call
│   ├── POST /chat/completions
│   └── Return answer string
└── main() — Entry point
    ├── Parse args
    ├── Call LLM
    └── Output JSON
```

## Dependencies

| Package | Purpose |
|---------|---------|
| `httpx` | Async HTTP client for API calls |
| `python-dotenv` | Load environment variables from file |

## Running the Agent

### Prerequisites

1. Create `.env.agent.secret`:

   ```bash
   cp .env.agent.example .env.agent.secret
   ```

2. Set your API key:

   ```
   LLM_API_KEY=your-openrouter-key
   LLM_API_BASE=https://openrouter.ai/api/v1
   LLM_MODEL=meta-llama/llama-3.3-70b-instruct:free
   ```

### Usage

```bash
# Basic usage
uv run agent.py "Your question here"

# Example
uv run agent.py "What is the capital of France?"

# Mock mode (testing without API)
LLM_MOCK_MODE=true uv run agent.py "Test question"
```

### Output Rules

- **stdout:** Only valid JSON
- **stderr:** Debug messages, errors, usage info
- **Exit code:** 0 on success

## Extending to Task 2

In Task 2, the agent will be extended with:

- Tool definitions (e.g., `read_file`, `list_files`, `query_api`)
- Tool calling loop (parse tool calls, execute, return results)
- Populated `tool_calls` array in output
