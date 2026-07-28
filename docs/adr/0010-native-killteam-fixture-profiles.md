# Native Kill Team fixture profiles

## Status

Accepted

Supported Kill Team saves are ingested without rewriting their native tags. A
versioned Python fixture setup profile maps native tags and stable anchors to
canonical roles, while Lua provides bounded generic queries for tags, exact
GUIDs, and global snap points. The loaded TTS scene remains the actionable
source of truth; the save file and expected GUIDs are test oracles only.

This preserves existing community saves and avoids mandatory retagging, at the
cost of maintaining and compatibility-testing one explicit profile per
supported fixture. Missing or ambiguous mappings fail closed, and fixture
profiles may not weaken visibility filtering or authorize arbitrary scene
enumeration.
