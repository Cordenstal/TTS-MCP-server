"""Guarded editing of numbered Tabletop Simulator JSON saves."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_SAVE_PATH = (
    Path.home()
    / "Documents"
    / "My Games"
    / "Tabletop Simulator"
    / "Saves"
    / "TS_Save_128.json"
)
MAX_SAVE_BYTES = 256 * 1024 * 1024
MAX_OPERATIONS = 200
MAX_POINTER_LENGTH = 2000
MAX_VALUE_BYTES = 4 * 1024 * 1024
_SAVE_NAME = re.compile(r"^TS_Save_[0-9]+\.json$", re.IGNORECASE)


def resolve_save_path(save_path: str = "") -> Path:
    """Resolve only a numbered save directly under TTS's local Saves folder."""
    requested = Path(save_path).expanduser() if save_path.strip() else DEFAULT_SAVE_PATH
    candidate = requested.resolve(strict=False)
    saves_root = (DEFAULT_SAVE_PATH.parent).resolve(strict=False)
    if candidate.parent != saves_root:
        raise ValueError(
            f"save_path must be a numbered file directly under {saves_root}"
        )
    if not _SAVE_NAME.fullmatch(candidate.name):
        raise ValueError("save_path must match TS_Save_<number>.json")
    return candidate


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> tuple[dict[str, Any], int, str]:
    if not path.is_file():
        raise FileNotFoundError(f"TTS save file does not exist: {path}")
    size = path.stat().st_size
    if size <= 0 or size > MAX_SAVE_BYTES:
        raise ValueError(f"save file size must be between 1 and {MAX_SAVE_BYTES} bytes")
    try:
        document = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"could not parse TTS save JSON: {exc}") from exc
    if not isinstance(document, dict):
        raise ValueError("TTS save JSON root must be an object")
    return document, size, _sha256(path)


def inspect_save(save_path: str = "") -> dict[str, Any]:
    path = resolve_save_path(save_path)
    document, size, digest = _read_json(path)
    objects = document.get("ObjectStates")
    return {
        "path": str(path),
        "file_name": path.name,
        "size_bytes": size,
        "sha256": digest,
        "save_name": document.get("SaveName"),
        "game_mode": document.get("GameMode"),
        "object_count": len(objects) if isinstance(objects, list) else None,
        "top_level_keys": sorted(str(key) for key in document),
    }


def _decode_pointer(pointer: str) -> list[str]:
    if not isinstance(pointer, str) or len(pointer) > MAX_POINTER_LENGTH:
        raise ValueError("JSON pointer must be a bounded string")
    if pointer == "":
        raise ValueError("replacing the entire save document is not allowed")
    if not pointer.startswith("/"):
        raise ValueError("JSON pointer must start with '/'")
    return [part.replace("~1", "/").replace("~0", "~") for part in pointer[1:].split("/")]


def _index_for(container: list[Any], token: str, *, allow_append: bool = False) -> int:
    if allow_append and token == "-":
        return len(container)
    try:
        index = int(token)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"array pointer segment must be an integer: {token!r}") from exc
    if index < 0 or index > len(container) or (index == len(container) and not allow_append):
        raise ValueError(f"array index is out of range: {token!r}")
    return index


def _parent(document: Any, tokens: list[str]) -> tuple[Any, str]:
    parent = document
    for token in tokens[:-1]:
        if isinstance(parent, dict):
            if token not in parent:
                raise ValueError(f"JSON pointer parent does not exist: {token!r}")
            parent = parent[token]
        elif isinstance(parent, list):
            parent = parent[_index_for(parent, token)]
        else:
            raise ValueError("JSON pointer traverses a scalar value")
    return parent, tokens[-1]


def _apply_operation(document: dict[str, Any], operation: dict[str, Any]) -> None:
    if not isinstance(operation, dict):
        raise ValueError("each save edit operation must be an object")
    kind = str(operation.get("op", "")).lower()
    if kind not in {"add", "replace", "remove"}:
        raise ValueError("save edit op must be add, replace, or remove")
    tokens = _decode_pointer(operation.get("path", ""))
    parent, token = _parent(document, tokens)
    if isinstance(parent, dict):
        if kind == "remove":
            if token not in parent:
                raise ValueError(f"JSON pointer does not exist: {operation['path']}")
            del parent[token]
        elif kind == "replace":
            if token not in parent:
                raise ValueError(f"JSON pointer does not exist: {operation['path']}")
            parent[token] = copy.deepcopy(operation.get("value"))
        else:
            parent[token] = copy.deepcopy(operation.get("value"))
        return
    if isinstance(parent, list):
        if kind == "add":
            parent.insert(_index_for(parent, token, allow_append=True), copy.deepcopy(operation.get("value")))
        elif kind == "replace":
            parent[_index_for(parent, token)] = copy.deepcopy(operation.get("value"))
        else:
            del parent[_index_for(parent, token)]
        return
    raise ValueError("JSON pointer parent is not an object or array")


def apply_operations(
    save_path: str,
    operations: list[dict[str, Any]],
    *,
    allow_irreversible: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Apply bounded JSON edits, backing up before any on-disk replacement."""
    if not isinstance(operations, list) or not operations:
        raise ValueError("operations must be a non-empty list")
    if len(operations) > MAX_OPERATIONS:
        raise ValueError(f"at most {MAX_OPERATIONS} operations are allowed")
    if not dry_run and not allow_irreversible:
        raise ValueError("set allow_irreversible=true to write the save file")

    path = resolve_save_path(save_path)
    document, size_before, digest_before = _read_json(path)
    updated = copy.deepcopy(document)
    for operation in operations:
        _apply_operation(updated, operation)
    encoded = json.dumps(updated, ensure_ascii=False, indent=2) + "\n"
    if len(encoded.encode("utf-8")) > MAX_SAVE_BYTES:
        raise ValueError("edited save would exceed the maximum supported size")

    result: dict[str, Any] = {
        "path": str(path),
        "dry_run": dry_run,
        "operation_count": len(operations),
        "size_before_bytes": size_before,
        "sha256_before": digest_before,
        "size_after_bytes": len(encoded.encode("utf-8")),
    }
    if dry_run:
        result["sha256_after"] = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        result["would_write"] = result["sha256_after"] != digest_before
        return result

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup = path.with_name(f".{path.name}.{timestamp}.bak")
    try:
        with path.open("rb") as source, backup.open("xb") as target:
            while True:
                chunk = source.read(1024 * 1024)
                if not chunk:
                    break
                target.write(chunk)
        temp_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False
            ) as temp:
                temp_name = temp.name
                temp.write(encoded)
                temp.flush()
                os.fsync(temp.fileno())
            os.replace(temp_name, path)
            temp_name = None
        finally:
            if temp_name:
                try:
                    Path(temp_name).unlink()
                except OSError:
                    pass
    except Exception:
        if backup.exists() and _sha256(backup) == digest_before:
            try:
                backup.unlink()
            except OSError:
                pass
        raise

    result.update({
        "backup_path": str(backup),
        "sha256_after": _sha256(path),
        "written": True,
    })
    return result

