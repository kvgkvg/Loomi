"""Validated role personalization policies with deterministic fallbacks."""

from __future__ import annotations

import json
import os
from typing import Any, Callable

from capture_pipeline.llm import FEATHERLESS_BASE_URL, FEATHERLESS_MODEL


_PRESETS = {
    "intern": {"role": "Intern", "goals": ["learn", "example", "constraint"], "detail_level": "guided", "ranking_weights": {"role": 0.10}, "explanation_style": "plain steps with glossary", "primary_actions": ["view example", "ask why"]},
    "developer": {"role": "Developer", "goals": ["implement", "debug", "constraint"], "detail_level": "technical", "ranking_weights": {"role": 0.10}, "explanation_style": "technical evidence", "primary_actions": ["copy prompt", "inspect revisions"]},
    "tech lead": {"role": "Tech Lead", "goals": ["trade-off", "reuse", "impact"], "detail_level": "architectural", "ranking_weights": {"role": 0.12}, "explanation_style": "trade-offs and alternatives", "primary_actions": ["review rationale", "assess impact"]},
    "manager": {"role": "Manager", "goals": ["outcome", "risk", "adoption"], "detail_level": "summary", "ranking_weights": {"role": 0.08}, "explanation_style": "outcome and risk summary", "primary_actions": ["view owner", "view adoption"]},
}
_CACHE: dict[str, dict] = {}


def clear_role_lens_cache() -> None:
    _CACHE.clear()


def _fallback() -> dict:
    return {**_PRESETS["developer"], "goals": list(_PRESETS["developer"]["goals"]), "primary_actions": list(_PRESETS["developer"]["primary_actions"]), "ranking_weights": dict(_PRESETS["developer"]["ranking_weights"]), "fallback": True}


def _validate(value: Any) -> dict:
    if not isinstance(value, dict):
        raise ValueError("role lens must be an object")
    required_strings = ("role", "detail_level", "explanation_style")
    if any(not isinstance(value.get(key), str) or not value[key].strip() for key in required_strings):
        raise ValueError("role lens strings are invalid")
    goals = value.get("goals")
    actions = value.get("primary_actions")
    weights = value.get("ranking_weights")
    if not isinstance(goals, list) or not all(isinstance(item, str) for item in goals):
        raise ValueError("role goals are invalid")
    if not isinstance(actions, list) or not all(isinstance(item, str) for item in actions):
        raise ValueError("role actions are invalid")
    if not isinstance(weights, dict) or set(weights) != {"role"}:
        raise ValueError("role weights are invalid")
    weight = weights["role"]
    if isinstance(weight, bool) or not isinstance(weight, (int, float)) or not 0 <= weight <= 0.2:
        raise ValueError("role weight is out of bounds")
    return {"role": value["role"].strip(), "goals": goals, "detail_level": value["detail_level"].strip(), "ranking_weights": {"role": float(weight)}, "explanation_style": value["explanation_style"].strip(), "primary_actions": actions, "fallback": False}


def resolve_role_lens(role: str | None, *, client_factory: Callable[..., Any] | None = None) -> dict:
    key = role.strip().lower() if isinstance(role, str) and role.strip() else "developer"
    if key in _CACHE:
        return _CACHE[key]
    if key in _PRESETS:
        result = {**_PRESETS[key], "fallback": False}
        _CACHE[key] = result
        return result
    api_key = os.getenv("FEATHERLESS_API_KEY")
    if not api_key:
        result = _fallback(); _CACHE[key] = result; return result
    if client_factory is None:
        from openai import OpenAI
        client_factory = OpenAI
    try:
        client = client_factory(base_url=FEATHERLESS_BASE_URL, api_key=api_key)
        response = client.chat.completions.create(
            model=FEATHERLESS_MODEL,
            temperature=0.1,
            messages=[
                {"role": "system", "content": "Create a role personalization lens. Return JSON keys role, goals, detail_level, ranking_weights with only role weight 0..0.2, explanation_style, primary_actions. No markdown."},
                {"role": "user", "content": role.strip()},
            ],
        )
        result = _validate(json.loads(response.choices[0].message.content))
    except Exception:
        result = _fallback()
    _CACHE[key] = result
    return result
