from __future__ import annotations

"""JSON-stdin adapter for Hermes one-shot mode.

The TTS gateway sends one JSON request containing a `messages` list. Hermes
does not expose the old `--stdin` interface, so this adapter converts that
request into a single non-interactive `hermes -z` invocation.
"""

import json
import os
import shutil
import subprocess
import sys


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError) as exc:
        print(json.dumps({"error": f"Invalid gateway request: {exc}"}))
        return 2

    messages = payload.get("messages", []) if isinstance(payload, dict) else []
    prompt_parts: list[str] = []
    for item in messages:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role", "user")).upper()
        content = item.get("content", "")
        if isinstance(content, list):
            content = " ".join(
                str(part.get("text", "")) for part in content
                if isinstance(part, dict) and part.get("text")
            )
        prompt_parts.append(f"{role}: {content}")
    prompt = "\n\n".join(prompt_parts).strip()
    if not prompt:
        prompt = str(payload.get("message", ""))
    if not prompt:
        print(json.dumps({"error": "No prompt supplied"}))
        return 2

    executable = shutil.which(os.getenv("HERMES_EXECUTABLE", "hermes"))
    if not executable:
        print(json.dumps({"error": "Hermes executable was not found on PATH"}))
        return 3

    try:
        completed = subprocess.run(
            # Global options must precede the top-level one-shot `-z` option.
            # Placing them after the prompt makes Hermes return its usage
            # error, which the gateway surfaces as HTTP 502.
            [executable, "--ignore-rules", "--no-restore-cwd", "-z", prompt],
            capture_output=True,
            text=True,
            timeout=float(os.getenv("AI_BACKEND_TIMEOUT", "120")),
            check=False,
        )
    except subprocess.TimeoutExpired:
        print(json.dumps({"error": "Hermes timed out"}))
        return 124
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        print(json.dumps({"error": detail[:1000] or f"Hermes exited with {completed.returncode}"}))
        return completed.returncode or 1
    print(json.dumps({"text": completed.stdout.strip()}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
