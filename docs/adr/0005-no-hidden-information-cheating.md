# ADR-0005: Prevent hidden-information cheating

## Status

Accepted

## Context

The AI can use the Blue player's camera at any time, including outside its
turn. Tabletop Simulator games may contain hidden hands, concealed zones,
face-down cards, private notes, or other information intended for specific
players.

## Decision

The configured control-plane player identity (Blue by default) must not view or
receive other players' hidden, private, or concealed information. Camera
movement, screenshots, object inspection, chat handling,
rules retrieval, and future RAG integrations must preserve this boundary.

The AI may receive a private message addressed to Player 2/Blue. It must not
receive private messages addressed to other players.

The AI may send private messages to individual players as Player 2/Blue.
Private outbound messages must identify the intended recipient and must not be
used to reveal information the AI was not permitted to know.

The system should prevent exposure before data reaches the model, not merely
instruct the model to ignore information after exposure. If the bridge cannot
reliably determine whether an observation is permitted, it must omit the
observation and ask the players or host for clarification.

The generic control plane has no host-only privileged-observer mode. Host
identity does not override the visibility boundary; any cooperative exception
must be designed as an explicit game-specific capability with its own policy.

## Consequences

Screenshot capture may require visibility-aware framing or redaction. Generic
object listing must not leak hidden contents or private metadata. Game-specific
adapters may be needed when TTS's generic visibility signals are insufficient.
The AI may have less information than a host, by design.

## Open questions

- Which TTS visibility/ownership signals can the bridge enforce reliably?
