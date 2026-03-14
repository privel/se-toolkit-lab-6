"""
Regression tests for Task 1: Call an LLM from Code.

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
    assert len(output["tool_calls"]) == 0, "'tool_calls' must be empty for Task 1"

    # Check exit code
    assert result.returncode == 0, f"Agent exited with code {result.returncode}"
