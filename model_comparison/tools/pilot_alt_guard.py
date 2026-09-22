"""Deny native tool use during the alternate-access admission check."""
import json
import sys

if __name__ == "__main__":
    # The only generation tools are fixed MCP endpoints; never inspect arguments.
    allowed = False
    if sys.argv[1:] == ["--cad"]:
        try:
            request = json.load(sys.stdin)
            allowed = request.get("tool_name") in ("mcp__cad__execute", "mcp__cad__submit")
        except (ValueError, TypeError):
            pass
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse", "permissionDecision": "allow" if allowed else "deny",
        "permissionDecisionReason": "Only the isolated CAD MCP endpoints are allowed."}}))
