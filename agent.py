#!/usr/bin/env python3
"""
CLI agent that sends questions to an LLM and returns structured JSON answers.
"""

import asyncio
import json
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

# Load environment variables from .env.agent.secret
load_dotenv(Path(__file__).parent / ".env.agent.secret")

LLM_API_KEY = os.getenv("LLM_API_KEY")
LLM_API_BASE = os.getenv("LLM_API_BASE")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen3-coder-plus")

# Mock mode: set to True to use mock responses (no API calls)
MOCK_MODE = os.getenv("LLM_MOCK_MODE", "false").lower() == "true"

TIMEOUT_SECONDS = 60


def log_debug(message: str) -> None:
    """Print debug messages to stderr."""
    print(f"[DEBUG] {message}", file=sys.stderr)


def get_mock_answer(question: str) -> str:
    """Return a mock answer for testing without API."""
    return f"Mock answer to: {question}"


async def call_llm(question: str) -> str:
    """Send a question to the LLM and return the answer."""
    if MOCK_MODE:
        log_debug("Mock mode enabled")
        return get_mock_answer(question)

    url = f"{LLM_API_BASE}/chat/completions"

    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": LLM_MODEL,
        "messages": [
            {
                "role": "system",
                "content": "You are a helpful assistant. Answer questions concisely and accurately.",
            },
            {"role": "user", "content": question},
        ],
    }

    log_debug(f"Sending request to {url}")
    log_debug(f"Model: {LLM_MODEL}")

    async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()

        data = response.json()
        answer = data["choices"][0]["message"]["content"]

        log_debug(f"Received response from LLM")

        return answer


async def main() -> int:
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: uv run agent.py <question>", file=sys.stderr)
        return 1

    question = sys.argv[1]
    log_debug(f"Question: {question}")

    try:
        answer = await call_llm(question)

        result = {
            "answer": answer,
            "tool_calls": [],
        }

        # Output only valid JSON to stdout
        print(json.dumps(result))

        return 0

    except Exception as e:
        log_debug(f"Error: {e}")
        error_result = {
            "answer": f"Error: {e}",
            "tool_calls": [],
        }
        print(json.dumps(error_result))
        return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
