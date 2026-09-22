"""Two native MCP tools backed exclusively by the existing CAD sandbox."""
import argparse
import json
from pathlib import Path
import sys
import time

from pilot_sandbox import execute_command
from pilot_snapshot import safe_snapshot


def serve(kit, output):
    work = output / "work"
    state_path = output / "tool_state.json"
    state = {"submitted": False, "tool_stopped": True, "tool_calls": 0, "records": []}

    def save():
        state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")

    save()
    for line in sys.stdin:
        request = json.loads(line)
        request_id = request.get("id")
        method = request.get("method")
        if request_id is None:
            continue
        result = {}
        try:
            if method == "initialize":
                result = {"protocolVersion": request["params"]["protocolVersion"],
                          "capabilities": {"tools": {}},
                          "serverInfo": {"name": "robotgen-isolated-cad", "version": "1"}}
            elif method == "tools/list":
                result = {"tools": [
                    {"name": "execute", "description": "Run a shell action only inside no-network/no-credential CAD sandbox. /kit read-only, /work writable, /cad/bin/python available. 60 seconds per action.",
                     "inputSchema": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"], "additionalProperties": False}},
                    {"name": "submit", "description": "Freeze and finish your one design attempt after writing the required files. No further execute calls are allowed.",
                     "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}}]}
            elif method == "tools/call":
                if state["submitted"]:
                    raise ValueError("already submitted")
                name = request["params"]["name"]
                if name == "submit":
                    state["submitted"] = True
                    state["submitted_snapshot"] = safe_snapshot(work)
                    save()
                    value = {"submitted": True}
                elif name == "execute":
                    command = request["params"].get("arguments", {}).get("command")
                    if not isinstance(command, str) or len(command) > 200000:
                        raise ValueError("invalid command")
                    state["tool_stopped"] = False
                    state["tool_calls"] += 1
                    save()
                    start = time.monotonic()
                    child = execute_command(command, kit=kit, writable_output=work, seconds=60, cad=True)
                    state["tool_stopped"] = True
                    value = {"exit_code": child.returncode, "stdout": child.stdout[:30000], "stderr": child.stderr[:10000]}
                    state["records"].append({"command": command, "argv": child.args, **value, "elapsed_s": time.monotonic()-start})
                    if not (output / "first").exists() and any(p.name != "operator_metadata.json" for p in work.iterdir()):
                        state["first_snapshot"] = safe_snapshot(work, output / "first")
                    save()
                else:
                    raise ValueError("unsupported tool")
                result = {"content": [{"type": "text", "text": json.dumps(value)}]}
            elif method != "ping":
                raise ValueError("unsupported method")
            response = {"jsonrpc": "2.0", "id": request_id, "result": result}
        except Exception as error:
            # Unknown stop state remains false; parent must refuse snapshot.
            save()
            response = {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32000, "message": type(error).__name__}}
        print(json.dumps(response), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--kit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    serve(args.kit.resolve(strict=True), args.output.resolve(strict=True))
