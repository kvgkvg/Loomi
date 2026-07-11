"""Featherless rationale extraction boundary."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable
from typing import Any


FEATHERLESS_BASE_URL = "https://api.featherless.ai/v1"
FEATHERLESS_MODEL = "zai-org/GLM-5.2"
SYSTEM_PROMPT = """Extract rationale from a changed AI knowledge asset.
Return exactly one JSON object with these fields:
- problem: non-empty string describing the problem solved
- failed_attempts: array of strings supported by the input
- constraints: array of strings supported by the input
- confidence: "auto"
Do not invent evidence. Use empty arrays when evidence is absent. No markdown."""


class RationaleError(RuntimeError):
    """Safe error raised when rationale extraction cannot produce valid data."""


def _strip_json_fence(content: str) -> str:
    match = re.fullmatch(r"\s*```(?:json)?\s*\n?(.*?)\n?```\s*", content, re.DOTALL)
    return match.group(1).strip() if match else content.strip()


def _validate_rationale(payload: Any) -> dict:
    if not isinstance(payload, dict):
        raise RationaleError("Featherless returned a non-object rationale")
    problem = payload.get("problem")
    failed_attempts = payload.get("failed_attempts")
    constraints = payload.get("constraints")
    confidence = payload.get("confidence")
    if not isinstance(problem, str) or not problem.strip():
        raise RationaleError("Rationale problem must be a non-empty string")
    if not isinstance(failed_attempts, list) or not all(
        isinstance(item, str) for item in failed_attempts
    ):
        raise RationaleError("Rationale failed_attempts must be a string list")
    if not isinstance(constraints, list) or not all(
        isinstance(item, str) for item in constraints
    ):
        raise RationaleError("Rationale constraints must be a string list")
    if confidence not in {"auto", "user_provided"}:
        raise RationaleError("Rationale confidence is invalid")
    return {
        "problem": problem.strip(),
        "failed_attempts": failed_attempts,
        "constraints": constraints,
        "confidence": confidence,
    }


def extract_rationale(
    content: str,
    raw_signal: str,
    *,
    client_factory: Callable[..., Any] | None = None,
) -> dict:
    """Call Featherless GLM-5.2 and return a validated rationale dictionary."""
    api_key = os.getenv("FEATHERLESS_API_KEY")
    if not api_key:
        raise RationaleError("FEATHERLESS_API_KEY is not set")
    if client_factory is None:
        from openai import OpenAI

        client_factory = OpenAI
    client = client_factory(base_url=FEATHERLESS_BASE_URL, api_key=api_key)
    try:
        response = client.chat.completions.create(
            model=FEATHERLESS_MODEL,
            temperature=0.1,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"Asset content:\n{content}\n\nSource signal:\n{raw_signal}",
                },
            ],
        )
        response_content = response.choices[0].message.content
    except Exception as exc:
        raise RationaleError("Featherless rationale request failed") from exc
    if not isinstance(response_content, str) or not response_content.strip():
        raise RationaleError("Featherless returned an empty rationale")
    try:
        payload = json.loads(_strip_json_fence(response_content))
    except (json.JSONDecodeError, TypeError) as exc:
        raise RationaleError("Featherless returned invalid rationale JSON") from exc
    return _validate_rationale(payload)
