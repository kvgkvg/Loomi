"""Grounded onboarding explanations backed by stored asset evidence."""

import json
import os
import urllib.error
import urllib.request


DEFAULT_MODEL = "gemini-3.1-flash-lite"
GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
TIMEOUT_SECONDS = 20


def get_pg_connection():
    """Load the team's shared database client lazily."""
    from db.client import get_pg_connection as connect

    return connect()


def _empty_result(message):
    return {"explanation": message, "cited_versions": [], "cited_constraints": []}


def _execute(cursor, query, params):
    try:
        cursor.execute(query, params)
    except Exception:
        cursor.execute(query.replace("%s", "?"), params)


def _value(row, name, index):
    if isinstance(row, dict):
        return row.get(name)
    keys = getattr(row, "keys", None)
    if callable(keys) and name in row.keys():
        return row[name]
    return row[index]


def _as_constraints(value):
    if value is None:
        return []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return [value]
    if isinstance(value, (list, tuple)):
        return [item for item in value if isinstance(item, str)]
    if isinstance(value, dict):
        return [str(item) for item in value.values() if isinstance(item, (str, int, float))]
    return []


def _load_evidence(connection, asset_id):
    cursor = connection.cursor()
    try:
        _execute(cursor, "SELECT id, title, type FROM assets WHERE id = %s", (asset_id,))
        asset_row = cursor.fetchone()
        if asset_row is None:
            return None
        asset = {
            "id": _value(asset_row, "id", 0),
            "title": _value(asset_row, "title", 1),
            "type": _value(asset_row, "type", 2),
        }
        _execute(
            cursor,
            """SELECT av.version_number, av.content, av.diff_summary,
                      r.problem, r.failed_attempts, r.constraints
                 FROM asset_versions av
                 LEFT JOIN rationale r ON r.version_id = av.id
                WHERE av.asset_id = %s
                ORDER BY av.version_number""",
            (asset_id,),
        )
        versions = []
        for row in cursor.fetchall():
            versions.append(
                {
                    "version_number": _value(row, "version_number", 0),
                    "content": _value(row, "content", 1),
                    "diff_summary": _value(row, "diff_summary", 2),
                    "problem": _value(row, "problem", 3),
                    "failed_attempts": _value(row, "failed_attempts", 4),
                    "constraints": _as_constraints(_value(row, "constraints", 5)),
                }
            )
        return {"asset": asset, "versions": versions}
    finally:
        cursor.close()


def _prompt(evidence, question):
    question_text = question.strip() if isinstance(question, str) and question.strip() else "No specific question."
    return (
        "Explain this organizational asset using only the evidence below. "
        "If the question cannot be answered from the evidence, say so. "
        "Return JSON with keys explanation (string), cited_versions (integer list), "
        "and cited_constraints (string list). Do not invent citations.\n\n"
        f"Evidence:\n{json.dumps(evidence, ensure_ascii=False, default=str)}\n\n"
        f"Question:\n{question_text}"
    )


def _call_gemini(prompt):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("missing Gemini API key")
    model = os.getenv("GEMINI_MODEL", DEFAULT_MODEL)
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2},
    }
    request = urllib.request.Request(
        GEMINI_ENDPOINT.format(model=model, key=api_key),
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        payload = json.loads(response.read().decode("utf-8"))
    text = payload["candidates"][0]["content"]["parts"][0]["text"]
    result = json.loads(text)
    if not isinstance(result, dict) or not isinstance(result.get("explanation"), str):
        raise ValueError("invalid Gemini response")
    if not isinstance(result.get("cited_versions"), list) or not isinstance(result.get("cited_constraints"), list):
        raise ValueError("invalid Gemini citations")
    return result


def _validated_result(model_result, evidence):
    if not isinstance(model_result.get("explanation"), str) or not model_result["explanation"].strip():
        raise ValueError("empty Gemini explanation")
    versions = {version["version_number"] for version in evidence["versions"]}
    constraints = {constraint for version in evidence["versions"] for constraint in version["constraints"]}
    cited_versions = [value for value in model_result["cited_versions"] if isinstance(value, int) and not isinstance(value, bool) and value in versions]
    cited_constraints = [value for value in model_result["cited_constraints"] if isinstance(value, str) and value in constraints]
    return {
        "explanation": model_result["explanation"],
        "cited_versions": cited_versions,
        "cited_constraints": cited_constraints,
    }


def explain_asset(asset_id: str, question: str = None) -> dict:
    if not isinstance(asset_id, str) or not asset_id.strip():
        return _empty_result("asset_id must be a non-empty string")
    connection = None
    try:
        connection = get_pg_connection()
        evidence = _load_evidence(connection, asset_id.strip())
        if evidence is None:
            return _empty_result("asset not found")
        return _validated_result(_call_gemini(_prompt(evidence, question)), evidence)
    except Exception:
        return _empty_result("unable to generate explanation")
    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass
