import math

W_COS, W_CONF, W_USE = 0.7, 0.2, 0.1
_USAGE_SATURATION = 20


def compute(cosine: float, confidence: str, usage_count: int) -> float:
    """Combine relevance + trust signals into a 0-1 score.

    cosine: similarity 0-1 (1 - chroma_distance).
    confidence: 'user_provided' | 'auto' (anything else treated as 'auto').
    usage_count: times the asset has been reused; boost saturates at 20.
    """
    conf_weight = 1.0 if confidence == "user_provided" else 0.6
    usage_boost = min(
        math.log1p(max(usage_count, 0)) / math.log1p(_USAGE_SATURATION), 1.0
    )
    return W_COS * cosine + W_CONF * conf_weight + W_USE * usage_boost


def role_adjusted(base_score: float, text: str, lens: dict) -> float:
    """Blend a bounded role keyword signal without overpowering semantics."""
    weight = min(max(float(lens.get("ranking_weights", {}).get("role", 0.0)), 0.0), 0.2)
    lowered = text.casefold()
    match = 1.0 if any(goal.casefold() in lowered for goal in lens.get("goals", []) if isinstance(goal, str)) else 0.0
    return min(max((1.0 - weight) * base_score + weight * match, 0.0), 1.0)
