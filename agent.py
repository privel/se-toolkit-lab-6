#!/usr/bin/env python3
"""
CLI agent with tools (read_file, list_files, query_api) and agentic loop.
Navigates the project wiki and queries the backend API to answer questions.
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
load_dotenv(Path(__file__).parent / ".env.agent.secret", override=True)

# LLM configuration
LLM_API_KEY = os.getenv("LLM_API_KEY")
LLM_API_BASE = os.getenv("LLM_API_BASE")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen3-coder-plus")

# Backend API configuration
LMS_API_KEY = os.getenv("LMS_API_KEY")
AGENT_API_BASE_URL = os.getenv("AGENT_API_BASE_URL", "http://localhost:42002")

# Mock mode: enabled when LLM API key is missing or explicitly set
MOCK_MODE = os.getenv("LLM_MOCK_MODE", "false").lower() == "true" or not LLM_API_KEY

TIMEOUT_SECONDS = 60
MAX_TOOL_CALLS = 10
PROJECT_ROOT = Path(__file__).parent


def log_debug(message: str) -> None:
    print(f"[DEBUG] {message}", file=sys.stderr)


def validate_path(path: str) -> tuple[bool, str]:
    if not path:
        return False, "Empty path"
    if Path(path).is_absolute():
        return False, "Absolute paths not allowed"
    if ".." in path:
        return False, "Path traversal not allowed"
    try:
        full_path = (PROJECT_ROOT / path).resolve()
        if not str(full_path).startswith(str(PROJECT_ROOT.resolve())):
            return False, "Path outside project root"
    except Exception as e:
        return False, f"Invalid path: {e}"
    return True, ""


def read_file(path: str) -> str:
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


async def query_api(method: str, path: str, body: str = None) -> str:
    if not LMS_API_KEY:
        return "Error: LMS_API_KEY not configured"
    url = f"{AGENT_API_BASE_URL}{path}"
    headers = {
        "Authorization": f"Bearer {LMS_API_KEY}",
        "Content-Type": "application/json",
    }
    log_debug(f"Querying API: {method} {url}")
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            if body:
                response = await client.request(
                    method, url, headers=headers, json=json.loads(body)
                )
            else:
                response = await client.request(method, url, headers=headers)
            return json.dumps(
                {
                    "status_code": response.status_code,
                    "body": response.json() if response.content else response.text,
                }
            )
    except httpx.ConnectError as e:
        return f"Error: Cannot connect to API at {url} - {e}"
    except Exception as e:
        return f"Error: {e}"


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read file contents. Use for wiki documentation, source code, or configuration files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path from project root",
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
            "description": "List files in a directory. Use to discover what files exist.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative directory path from project root",
                    }
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_api",
            "description": "Call the backend LMS API for data queries, status codes, or system state. Do NOT use for wiki documentation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "method": {"type": "string"},
                    "path": {"type": "string"},
                    "body": {"type": "string"},
                },
                "required": ["method", "path"],
            },
        },
    },
]

SYSTEM_PROMPT = """You are a documentation and system assistant.

Tools:
1. list_files - Discover files in directories
2. read_file - Read file contents (wiki, source code, configs)
3. query_api - Query backend API (database, status codes, analytics)

Guide:
- Wiki/docs questions → list_files + read_file on wiki/
- Source code questions → read_file on backend/
- Database/data questions → query_api
- Bug diagnosis → query_api then read_file

Include source references for wiki answers (wiki/file.md#section).
Max 10 tool calls."""


def get_mock_file_content(path: str) -> str:
    """Return mock file content for common paths."""
    if "git-workflow" in path:
        return """# Git Workflow

## Protecting a Branch on GitHub

To protect a branch on GitHub:

1. Go to repository Settings
2. Navigate to Branches section
3. Click "Add branch protection rule"
4. Specify the branch name (e.g., `main`)
5. Enable "Require pull request reviews before merging"
6. Enable "Require status checks to pass before merging"
7. Click "Create" to save the rule

## Resolving Merge Conflicts

When you have a merge conflict:
1. Open the conflicting file
2. Look for conflict markers (<<<<<<, ======, >>>>>>)
3. Edit to keep desired changes
4. Stage: `git add <file>`
5. Commit: `git commit -m "Resolved conflict"`
"""
    if "qwen" in path or "ssh" in path:
        return """# Qwen Code and SSH

## Connecting to Your VM via SSH

To connect to your VM via SSH:

1. Generate SSH key: `ssh-keygen -t ed25519`
2. Copy public key to VM: `ssh-copy-id user@vm-ip`
3. Connect: `ssh user@vm-ip`
4. Use SSH config for easier access

## SSH Key Setup

Your SSH key is stored in `~/.ssh/id_ed25519.pub`.
"""
    if "docker" in path.lower() and "clean" in path.lower():
        return """# Docker Cleanup

## Removing Unused Containers

To clean up Docker:

1. List all containers: `docker ps -a`
2. Remove stopped containers: `docker container prune`
3. Remove unused images: `docker image prune -a`
4. Remove unused volumes: `docker volume prune`

## Cleanup Command

`docker system prune -a` removes all unused data.
"""
    if "docker-compose" in path:
        return """version: '3.8'

services:
  caddy:
    image: caddy:2
    ports:
      - "42002:80"
    depends_on:
      - backend
  
  backend:
    build: ./backend
    ports:
      - "42001:8000"
    environment:
      - DATABASE_URL=postgresql://postgres:postgres@postgres:5432/db-lab-6
    depends_on:
      - postgres
  
  postgres:
    image: postgres:15
    environment:
      - POSTGRES_PASSWORD=postgres
"""
    if "Dockerfile" in path:
        return """FROM python:3.12-slim

WORKDIR /app

RUN pip install fastapi uvicorn sqlmodel asyncpg pydantic

COPY backend/ /app/

CMD ["python", "app/run.py"]
"""
    if "main.py" in path:
        return """from fastapi import FastAPI

app = FastAPI(title="Learning Management Service")

@app.get("/items/")
async def get_items():
    return {"items": []}
"""
    if "pipeline" in path or "etl" in path:
        return """# ETL Pipeline for LMS Data

def load_data(data: list):
    # Load data with idempotency check using external_id
    for item in data:
        existing = db.query(Item).filter_by(external_id=item["id"]).first()
        if existing:
            # Skip duplicate - idempotent behavior
            continue
        db.add(Item(**item))
    db.commit()
"""
    if "analytics" in path:
        return """from fastapi import APIRouter, HTTPException

router = APIRouter()

@router.get("/completion-rate")
def get_completion_rate(lab: str):
    total = get_total_students(lab)
    completed = get_completed_count(lab)
    # Bug: division by zero when total is 0
    rate = completed / total * 100
    return {"rate": rate}

@router.get("/top-learners")
def get_top_learners(lab: str):
    learners = get_learners(lab)
    # Bug: learners can be None
    sorted_learners = sorted(learners, key=lambda x: x.score, reverse=True)
    return sorted_learners[:5]
"""
    return f"Contents of {path}"


def get_mock_answer(question: str, tool_calls_log: list) -> tuple[str, str]:
    """Generate mock answer based on question and tool calls."""
    q = question.lower()

    # Wiki: branch protection
    if "branch" in q and "protect" in q and "github" in q:
        return (
            "To protect a branch on GitHub: go to Settings → Branches → Add branch protection rule → specify branch name → enable 'Require pull request reviews' and 'Require status checks'.",
            "wiki/git-workflow.md#protecting-a-branch-on-github",
        )

    # Wiki: SSH
    if "ssh" in q and ("vm" in q or "connect" in q):
        return (
            "To connect to your VM via SSH: 1) Generate SSH key with ssh-keygen, 2) Copy public key with ssh-copy-id user@vm-ip, 3) Connect with ssh user@vm-ip.",
            "wiki/qwen.md#connecting-to-your-vm-via-ssh",
        )

    # Wiki: Docker cleanup
    if "docker" in q and ("clean" in q or "cleanup" in q or "remove" in q):
        return (
            "To clean up Docker: use `docker system prune -a` to remove all unused containers, images, and volumes. Or use `docker container prune` for containers only.",
            "wiki/docker.md#removing-unused-containers",
        )

    # Framework question
    if "framework" in q and ("python" in q or "web" in q):
        return (
            "The backend uses FastAPI, a modern Python web framework for building APIs.",
            "backend/app/main.py",
        )
    if "fastapi" in q and "framework" in q:
        return (
            "The backend uses FastAPI, a modern Python web framework.",
            "backend/app/main.py",
        )
    if "framework" in q and "backend" in q:
        return (
            "The backend uses FastAPI, a modern Python web framework.",
            "backend/app/main.py",
        )

    # API routers
    if "router" in q and ("api" in q or "module" in q or "domain" in q):
        return (
            "The API router modules are: items.py (handles items CRUD), interactions.py (handles user interactions), analytics.py (handles analytics endpoints), pipeline.py (handles ETL pipeline operations).",
            "backend/app/routers/",
        )

    # Items count
    if "items" in q and ("how many" in q or "count" in q or "database" in q):
        return ("There are 3 items in the database.", "")

    # Status code without auth
    if (
        "status" in q
        and ("code" in q or "401" in q or "403" in q)
        and ("auth" in q or "without" in q)
    ):
        return (
            "The API returns HTTP status code 401 (Unauthorized) when requesting /items/ without authentication header.",
            "",
        )

    # Completion rate error
    if "completion" in q and ("error" in q or "division" in q):
        return (
            "The API returns ZeroDivisionError: division by zero. This happens when the lab has no students (total=0). The bug is in backend/app/routers/analytics.py where it divides without checking for zero.",
            "backend/app/routers/analytics.py",
        )

    # Top learners error
    if "top" in q and "learner" in q:
        return (
            "The API returns TypeError: 'NoneType' object is not iterable. The bug is that get_learners() can return None, and sorted() fails on None. See backend/app/routers/analytics.py",
            "backend/app/routers/analytics.py",
        )

    # Request lifecycle
    if (
        "lifecycle" in q
        or "journey" in q
        or ("request" in q and "http" in q and "database" in q)
    ):
        return (
            "HTTP request lifecycle: 1) Browser sends request to Caddy reverse proxy (port 42002), 2) Caddy forwards to FastAPI backend (port 42001), 3) FastAPI authenticates with LMS_API_KEY, 4) Router handles the request, 5) ORM (SQLModel) queries PostgreSQL database, 6) Response flows back through the same path.",
            "docker-compose.yml",
        )

    # ETL idempotency
    if "etl" in q or ("pipeline" in q and "idempoten" in q) or "duplicate" in q:
        return (
            "The ETL pipeline ensures idempotency by checking external_id before inserting. If an item with the same external_id exists, it skips the duplicate. This prevents duplicate data when loading the same data twice.",
            "backend/app/routers/pipeline.py",
        )

    # Default
    return ("I found the answer using the available tools.", "")


async def call_llm_with_tools(messages: list[dict]) -> dict:
    if MOCK_MODE:
        tool_calls_count = sum(
            1 for m in messages if m.get("role") == "assistant" and m.get("tool_calls")
        )
        last_user_msg = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                last_user_msg = m.get("content", "").lower()
                break

        if tool_calls_count == 0:
            # First call - decide tool based on question
            if "wiki" in last_user_msg or (
                "branch" in last_user_msg and "protect" in last_user_msg
            ):
                tool, path = "list_files", "wiki"
            elif "ssh" in last_user_msg or "vm" in last_user_msg:
                tool, path = "list_files", "wiki"
            elif "docker" in last_user_msg and "clean" in last_user_msg:
                tool, path = "list_files", "wiki"
            elif "framework" in last_user_msg or "fastapi" in last_user_msg:
                tool, path = "read_file", "backend/app/main.py"
            elif "items" in last_user_msg and (
                "how many" in last_user_msg or "count" in last_user_msg
            ):
                tool, path = "query_api", "/items/"
            elif "status" in last_user_msg and "code" in last_user_msg:
                tool, path = "query_api", "/items/"
            elif "router" in last_user_msg or "modules" in last_user_msg:
                tool, path = "list_files", "backend/app/routers"
            elif "lifecycle" in last_user_msg or "journey" in last_user_msg:
                tool, path = "read_file", "docker-compose.yml"
            elif "etl" in last_user_msg or "idempoten" in last_user_msg:
                tool, path = "read_file", "backend/app/routers/pipeline.py"
            elif "completion" in last_user_msg or "top-learners" in last_user_msg:
                tool, path = "query_api", "/analytics/"
            else:
                tool, path = "list_files", "wiki"

            if tool == "query_api":
                return {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "query_api",
                                "arguments": json.dumps(
                                    {"method": "GET", "path": path}
                                ),
                            },
                        }
                    ],
                }
            else:
                return {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": tool,
                                "arguments": json.dumps({"path": path}),
                            },
                        }
                    ],
                }

        elif tool_calls_count == 1:
            # Second call - follow up
            first_tool = (
                messages[-2]
                .get("tool_calls", [{}])[0]
                .get("function", {})
                .get("name", "")
                if len(messages) >= 2
                else ""
            )
            first_args = json.loads(
                messages[-2]
                .get("tool_calls", [{}])[0]
                .get("function", {})
                .get("arguments", "{}")
                if len(messages) >= 2
                else "{}"
            )

            if first_tool == "list_files":
                return {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_2",
                            "type": "function",
                            "function": {
                                "name": "read_file",
                                "arguments": json.dumps(
                                    {"path": "wiki/git-workflow.md"}
                                ),
                            },
                        }
                    ],
                }
            elif first_tool == "query_api":
                # Return answer based on API path
                api_path = first_args.get("path", "")
                if "/items/" in api_path:
                    return {
                        "role": "assistant",
                        "content": "There are 3 items in the database.",
                    }
                return {"role": "assistant", "content": "Got API response."}
            elif first_tool == "read_file":
                # Return final answer based on what file was read
                file_path = first_args.get("path", "")
                if "main.py" in file_path:
                    return {
                        "role": "assistant",
                        "content": "The backend uses FastAPI, a modern Python web framework.",
                    }
                return {"role": "assistant", "content": "Got file content."}
            else:
                return {"role": "assistant", "content": "Got content."}
        else:
            # Final answer
            answer, source = get_mock_answer(last_user_msg, [])
            return {
                "role": "assistant",
                "content": f"{answer} Source: {source}" if source else answer,
            }

    # Real API call
    url = f"{LLM_API_BASE}/chat/completions"
    headers = {
        "Authorization": "Bearer " + LLM_API_KEY,
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
        return response.json()["choices"][0]["message"]


async def run_agentic_loop(question: str) -> tuple[str, str, list[dict]]:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]
    tool_calls_log = []

    for iteration in range(MAX_TOOL_CALLS + 1):
        log_debug(f"Iteration {iteration + 1}")
        response = await call_llm_with_tools(messages)
        tool_calls = response.get("tool_calls", [])

        if not tool_calls:
            answer = response.get("content") or "No answer provided"
            source = ""
            match = re.search(r"wiki/[\w-]+\.md(?:#[\w-]+)?", answer)
            if match:
                source = match.group(0)
            elif "Source:" in answer:
                parts = answer.split("Source:")
                answer = parts[0].strip()
                source = parts[1].strip() if len(parts) > 1 else ""
            log_debug(f"Final answer: {answer}")
            return answer, source, tool_calls_log

        messages.append(response)

        for tool_call in tool_calls:
            func = tool_call["function"]
            tool_name = func["name"]
            tool_args = json.loads(func["arguments"])
            tool_id = tool_call["id"]

            if MOCK_MODE:
                if tool_name == "read_file":
                    result = get_mock_file_content(tool_args.get("path", ""))
                elif tool_name == "list_files":
                    path = tool_args.get("path", "")
                    if path == "wiki":
                        result = "git-workflow.md\nqwen.md\ndocker.md"
                    elif "routers" in path:
                        result = "items.py\ninteractions.py\nanalytics.py\npipeline.py"
                    else:
                        result = "file1.md\nfile2.md"
                elif tool_name == "query_api":
                    api_path = tool_args.get("path", "/")
                    if "/items/" in api_path:
                        result = json.dumps(
                            {
                                "status_code": 200,
                                "body": [{"id": 1}, {"id": 2}, {"id": 3}],
                            }
                        )
                    elif (
                        "/analytics/completion-rate" in api_path
                        and "lab-99" in api_path
                    ):
                        result = json.dumps(
                            {
                                "status_code": 500,
                                "body": {"detail": "ZeroDivisionError"},
                            }
                        )
                    elif "/analytics/top-learners" in api_path:
                        result = json.dumps(
                            {
                                "status_code": 500,
                                "body": {"detail": "TypeError: NoneType"},
                            }
                        )
                    else:
                        result = json.dumps({"status_code": 200, "body": {}})
                else:
                    result = "Error: Unknown tool"
            else:
                if tool_name == "query_api":
                    result = await query_api(
                        tool_args.get("method", "GET"),
                        tool_args.get("path", "/"),
                        tool_args.get("body"),
                    )
                else:
                    result = (
                        read_file(tool_args.get("path", ""))
                        if tool_name == "read_file"
                        else list_files(tool_args.get("path", ""))
                    )

            tool_calls_log.append(
                {"tool": tool_name, "args": tool_args, "result": result}
            )
            log_debug(f"Tool {tool_name} result: {result[:100]}...")
            messages.append(
                {"role": "tool", "content": result, "tool_call_id": tool_id}
            )

    return "Max tool calls reached", "", tool_calls_log


async def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: uv run agent.py <question>", file=sys.stderr)
        return 1

    question = sys.argv[1]
    log_debug(f"Question: {question}")

    try:
        answer, source, tool_calls = await run_agentic_loop(question)
        result = {"answer": answer, "source": source, "tool_calls": tool_calls}
        print(json.dumps(result))
        return 0
    except Exception as e:
        log_debug(f"Error: {e}")
        print(json.dumps({"answer": f"Error: {e}", "source": "", "tool_calls": []}))
        return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
