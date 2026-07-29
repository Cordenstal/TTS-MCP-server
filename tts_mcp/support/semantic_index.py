from __future__ import annotations

import re
from typing import Any


def _tokens(value: Any) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", str(value or "").lower()) if token}


def score_object_reference(reference: str, obj: dict[str, Any]) -> tuple[float, list[str]]:
    """Score a scene object against a human reference and explain the score."""
    query = _tokens(reference)
    if not query:
        return 0.0, []
    guid = str(obj.get("guid") or "").lower()
    name = str(obj.get("name") or "")
    object_type = str(obj.get("type") or "")
    description = str(obj.get("description") or "")
    tags = [str(tag) for tag in obj.get("tags") or []]
    name_tokens = _tokens(name)
    tag_tokens = set().union(*(_tokens(tag) for tag in tags)) if tags else set()
    type_tokens = _tokens(object_type)
    description_tokens = _tokens(description)

    score = 0.0
    evidence: list[str] = []
    if str(reference).strip().lower() == guid and guid:
        score += 100
        evidence.append("exact GUID")
    if query <= name_tokens:
        score += 70
        evidence.append("all reference words match the name")
    elif query & name_tokens:
        score += 35 * len(query & name_tokens) / len(query)
        evidence.append("some reference words match the name")
    if query <= tag_tokens:
        score += 60
        evidence.append("all reference words match tags")
    elif query & tag_tokens:
        score += 30 * len(query & tag_tokens) / len(query)
        evidence.append("some reference words match tags")
    if query & type_tokens:
        score += 20 * len(query & type_tokens) / len(query)
        evidence.append("reference words match object type")
    if query & description_tokens:
        score += 10 * len(query & description_tokens) / len(query)
        evidence.append("reference words match description")
    return round(min(score, 100.0), 3), evidence


def rank_scene_objects(reference: str, objects: list[dict[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    for obj in objects:
        score, evidence = score_object_reference(reference, obj)
        if score <= 0:
            continue
        ranked.append({"score": score, "evidence": evidence, "object": obj})
    ranked.sort(key=lambda item: (-item["score"], str(item["object"].get("guid", ""))))
    return ranked[: max(1, min(limit, 50))]
