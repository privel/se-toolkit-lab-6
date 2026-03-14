# Task 1: Call an LLM from Code

## LLM Provider

**Provider:** OpenRouter  
**Model:** `meta-llama/llama-3.3-70b-instruct:free`  
**API Base:** `https://openrouter.ai/api/v1`

**Why OpenRouter:**
- Free tier available (50 requests/day)
- No credit card required
- OpenAI-compatible API
- Works without VM setup

## Agent Structure

### Components

1. **Environment Loading**
   - Read `.env.agent.secret` using `python-dotenv`
   - Extract `LLM_API_KEY`, `LLM_API_BASE`, `LLM_MODEL`

2. **CLI Interface**
   - Parse command-line argument (question)
   - Validate input (non-empty question)

3. **LLM Client**
   - Async HTTP request using `httpx`
   - POST to `/chat/completions` endpoint
   - OpenAI-compatible payload format
   - 60-second timeout

4. **Response Formatting**
   - Parse LLM response JSON
   - Extract answer from `choices[0].message.content`
   - Output: `{"answer": "...", "tool_calls": []}`

### Data Flow

```
CLI argument → question
     ↓
Load .env.agent.secret → LLM_API_KEY, LLM_API_BASE, LLM_MODEL
     ↓
POST /chat/completions → LLM API
     ↓
Parse response → answer
     ↓
JSON output → stdout
```

## Error Handling

| Error | Handling |
|-------|----------|
| Missing `.env.agent.secret` | Log to stderr, exit 1 |
| Empty question | Log usage to stderr, exit 1 |
| API error (4xx/5xx) | Log to stderr, return error in JSON |
| Timeout (>60s) | httpx timeout, log to stderr |

## Testing

**Test file:** `backend/tests/unit/test_agent_task1.py`

**Test case:**
- Run `agent.py` with a test question
- Parse stdout as JSON
- Assert `answer` field exists and is non-empty
- Assert `tool_calls` field exists and is empty array
