"""
Regression tests for Task 1 & Task 2: Agent with tools.

Tests verify that agent.py outputs valid JSON with required fields.
.
"""

import json
import os
import subprocess
import sys
from pathlib import Path


def test_agent_outputs_valid_json():
    """Test that agent.py outputs valid JSON with answer and tool_calls fields."""
    agent_path = Path(__file__).parent / "agent.py"

    # Run agent with mock mode enabled
    env = os.environ.copy()
    env["LLM_MOCK_MODE"] = "true"
    env["LLM_API_BASE"] = "https://openrouter.ai/api/v1"
    env["LLM_MODEL"] = "meta-llama/llama-3.3-70b-instruct:free"

    # Run agent with a simple test question
    result = subprocess.run(
        [sys.executable, str(agent_path), "What is 2+2?"],
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
        cwd=agent_path.parent,
    )

    # Debug: print stderr if stdout is empty
    if not result.stdout.strip():
        print(f"stderr: {result.stderr}", file=sys.stderr)

    # Parse stdout as JSON
    output = json.loads(result.stdout)

    # Check required fields
    assert "answer" in output, "Missing 'answer' field in output"
    assert isinstance(output["answer"], str), "'answer' must be a string"
    assert len(output["answer"]) > 0, "'answer' must not be empty"

    assert "tool_calls" in output, "Missing 'tool_calls' field in output"
    assert isinstance(output["tool_calls"], list), "'tool_calls' must be an array"

    # Check exit code
    assert result.returncode == 0, f"Agent exited with code {result.returncode}"


def test_documentation_agent_uses_read_file():
    """Test that the agent uses read_file tool for documentation questions."""
    agent_path = Path(__file__).parent / "agent.py"

    env = os.environ.copy()
    env["LLM_MOCK_MODE"] = "true"

    # Question about git merge conflicts should trigger read_file
    result = subprocess.run(
        [sys.executable, str(agent_path), "How do you resolve a merge conflict?"],
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
        cwd=agent_path.parent,
    )

    output = json.loads(result.stdout)

    # Check that tool_calls contains read_file
    assert "tool_calls" in output, "Missing 'tool_calls' field"
    assert len(output["tool_calls"]) > 0, "Expected at least one tool call"

    tool_names = [call.get("tool") for call in output["tool_calls"]]
    assert "read_file" in tool_names, (
        f"Expected read_file in tool_calls, got: {tool_names}"
    )

    # Check source field exists
    assert "source" in output, "Missing 'source' field"


def test_documentation_agent_uses_list_files():
    """Test that the agent uses list_files tool to discover wiki files."""
    agent_path = Path(__file__).parent / "agent.py"

    env = os.environ.copy()
    env["LLM_MOCK_MODE"] = "true"

    # Question about wiki files should trigger list_files
    result = subprocess.run(
        [sys.executable, str(agent_path), "What files are in the wiki?"],
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
        cwd=agent_path.parent,
    )

    output = json.loads(result.stdout)

    # Check that tool_calls contains list_files
    assert "tool_calls" in output, "Missing 'tool_calls' field"
    assert len(output["tool_calls"]) > 0, "Expected at least one tool call"

    tool_names = [call.get("tool") for call in output["tool_calls"]]
    assert "list_files" in tool_names, (
        f"Expected list_files in tool_calls, got: {tool_names}"
    )

    # Check that list_files was called with wiki path
    list_files_call = next(
        (c for c in output["tool_calls"] if c.get("tool") == "list_files"), None
    )
    assert list_files_call is not None, "list_files call not found"
    assert list_files_call.get("args", {}).get("path") == "wiki", (
        "list_files should be called with path='wiki'"
    )
