"""Version-pinned transcript-record knowledge for Claude Code session JSONL.

Every field name here was reverse-engineered — there is NO published schema
(SYNTHESIS 1.4; Codex's docs explicitly warn the format is not a stable
interface). Treat this module the way patterns.py treats UI copy: versioned
SETS + a self-test that fails LOUDLY when a session provably ran and none of
our record kinds matched (SPEC rule 6, applied to the disk channel).

Verified live on claude 2.1.222 / macOS against:
  ~/.claude/projects/<mangled-cwd>/<session-id>.jsonl
"""

COMPAT_RANGE = ("2.1.222", "2.1.222")  # [min, max] verified

# --- record kinds we key state off ------------------------------------------
# top-level "type" values seen: mode, permission-mode, bridge-session,
# file-history-snapshot, user, attachment, last-prompt, ai-title, assistant,
# system.  "system" carries a "subtype" that does the real work.

BOOTSTRAP_TYPES = {"mode", "permission-mode", "bridge-session", "ai-title"}
SYS_TURN_END = "turn_duration"        # {"durationMs":..,"messageCount":..} — turn ended
SYS_HOOK_SUMMARY = "stop_hook_summary"  # proof a Stop hook actually ran
SYS_COMPACT = "compact_boundary"      # explains long silent gaps

# Tools whose *pending* state is a user-input wait, not a permission wait.
# The transcript names the tool — a discriminator the screen channel lacks.
INPUT_TOOLS = {"AskUserQuestion", "ExitPlanMode"}

# Denial is recorded RETROSPECTIVELY on the tool_result record.
DENIAL_KINDS = {"user-rejected", "user-rejected-with-message"}
DENIAL_RESULT_TEXT = "The user doesn't want to proceed with this tool use"
INTERRUPT_TEXT = "[Request interrupted by user"

RECOGNIZED_TYPES = BOOTSTRAP_TYPES | {
    "user", "assistant", "system", "attachment", "last-prompt",
    "file-history-snapshot", "summary", "queued-command",
}


def classify(rec: dict) -> dict:
    """Pure per-record classification. No state decisions here — the engine
    composes records over time (SPEC rule 1)."""
    t = rec.get("type")
    sub = rec.get("subtype")
    out = {
        "type": t,
        "subtype": sub,
        "ts": rec.get("timestamp"),
        "uuid": rec.get("uuid"),
        "parent": rec.get("parentUuid"),
        "session_id": rec.get("sessionId") or rec.get("session_id"),
        "forked_from": rec.get("forkedFrom"),
        "known": t in RECOGNIZED_TYPES,
        "is_prompt": False,
        "turn_end": False,
        "compact": False,
        "hook_summary": False,
        "tool_use": [],       # [(id, name)]
        "tool_results": [],   # [(id, denied_bool, denial_kind)]
        "interrupted": False,
    }
    if t == "system":
        out["turn_end"] = sub == SYS_TURN_END
        out["compact"] = sub == SYS_COMPACT
        out["hook_summary"] = sub == SYS_HOOK_SUMMARY
        if out["turn_end"]:
            out["duration_ms"] = rec.get("durationMs")
        return out

    msg = rec.get("message") or {}
    content = msg.get("content")

    if t == "assistant" and isinstance(content, list):
        for blk in content:
            if isinstance(blk, dict) and blk.get("type") == "tool_use":
                out["tool_use"].append((blk.get("id"), blk.get("name")))
        return out

    if t == "user":
        if isinstance(content, str):
            out["is_prompt"] = True          # a human prompt submission
            out["prompt"] = content[:120]
        elif isinstance(content, list):
            for blk in content:
                if not isinstance(blk, dict):
                    continue
                if blk.get("type") == "tool_result":
                    kind = rec.get("toolDenialKind")
                    denied = bool(kind) or (
                        isinstance(blk.get("content"), str)
                        and DENIAL_RESULT_TEXT in blk["content"])
                    out["tool_results"].append(
                        (blk.get("tool_use_id"), denied, kind))
                elif blk.get("type") == "text":
                    if INTERRUPT_TEXT in (blk.get("text") or ""):
                        out["interrupted"] = True
                    else:
                        # a plain-text user block with no tool_result is also a
                        # prompt in some renderings; treat conservatively.
                        out["is_prompt"] = True
                        out["prompt"] = (blk.get("text") or "")[:120]
    return out


class SchemaSelfTest:
    """SPEC rule 6 for the disk channel: a session that provably produced
    records with zero recognized kinds must fail loudly, not return unknown."""

    def __init__(self):
        self.records = 0
        self.recognized = 0
        self.unknown_types = set()
        self.turn_ends = 0

    def observe(self, rec: dict, cls: dict):
        self.records += 1
        if cls["known"]:
            self.recognized += 1
        else:
            self.unknown_types.add(str(rec.get("type")))
        if cls["turn_end"]:
            self.turn_ends += 1

    def verdict(self) -> dict:
        ok = self.records == 0 or self.recognized > 0
        return {
            "records": self.records,
            "recognized": self.recognized,
            "unknown_types": sorted(self.unknown_types),
            "turn_end_records": self.turn_ends,
            "schema_ok": ok,
            "compat": list(COMPAT_RANGE),
        }
