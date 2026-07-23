# Observation and spatial reasoning

## Authoritative state

The structured bridge should answer exact questions:

- What objects exist?
- Which GUID, type, name, tags, and state does each have?
- Where is the center and what are the world-space bounds?
- Is it moving, resting, locked, held, inside a zone, or inside a container?
- What is the final state after an action?

The first observation milestone is to extend `mcp_object_summary` with bounds,
velocity, smooth targets, resting state, transform axes, zone membership, and
container information.

## Spatial queries

Add queries that operate on the live scene rather than forcing the model to
perform fragile geometry itself:

- nearest object to a point or reference object;
- objects within a radius or box;
- objects overlapping a bounds volume;
- ray/box/sphere cast results;
- distance and relative transform;
- placement clearance and collision checks;
- objects occupying a scripting zone;
- snap points and nearest snap point.

## Visual state

Screenshots are on-demand evidence, not a video stream. Each capture should
include its rectangle, dimensions, timestamp, camera settings, and health
status. A useful visual workflow is:

1. Calibrate the screen rectangle containing TTS.
2. Inspect structured state.
3. Move/focus the camera using object bounds.
4. Wait for the camera and physics to settle.
5. Capture the image.
6. Execute the bounded action.
7. Re-inspect and capture an after image when visual confirmation matters.

Annotations such as GUID labels and bounds should be rendered into a copy of
the screenshot in Python, not injected into the TTS scene.

## What vision must not decide alone

Do not use a screenshot alone to determine:

- exact GUID identity;
- exact position or rotation;
- whether an object is locked;
- whether an object is hidden in a container or hand;
- whether a move has finished;
- whether a destructive action is safe.
