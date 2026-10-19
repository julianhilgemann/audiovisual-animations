"""Send Python code to a running Blender through the Blender Lab "MCP" add-on socket.

The add-on listens on localhost:9876 (GUI: auto-starts with Blender; headless:
`blender -b file.blend --online-mode -c blender_mcp`). Code runs on Blender's main
thread; assign a JSON-serializable dict to `result` to get data back.

Examples:
    python tools/blender_bridge.py --ping
    python tools/blender_bridge.py -c "import bpy; result = {'objects': [o.name for o in bpy.data.objects]}"
    python tools/blender_bridge.py -f some_script.py --timeout 300

Exit codes: 0 ok, 1 Blender returned an error, 2 Blender not reachable.
Stdlib only, so it runs with any Python >= 3.8.
"""

import argparse
import json
import socket
import sys

PING_CODE = (
    "import bpy\n"
    "result = {'blender': bpy.app.version_string, 'file': bpy.data.filepath, "
    "'scene': bpy.context.scene.name, 'background': bpy.app.background}\n"
)


def send(code: str, host: str = "localhost", port: int = 9876, timeout: float = 60.0,
         strict_json: bool = False) -> dict:
    """Execute *code* in Blender and return the decoded response dict."""
    payload = json.dumps({"type": "execute", "code": code, "strict_json": strict_json}).encode("utf-8") + b"\0"
    with socket.create_connection((host, port), timeout=timeout) as conn:
        conn.sendall(payload)
        chunks = []
        while True:
            chunk = conn.recv(65536)
            if not chunk:
                break
            chunks.append(chunk)
            if chunk.endswith(b"\0"):
                break
    return json.loads(b"".join(chunks).rstrip(b"\0").decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("-c", "--code", help="Python code to execute")
    src.add_argument("-f", "--file", help="file containing Python code to execute")
    src.add_argument("--ping", action="store_true", help="report Blender version and open file")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=9876)
    parser.add_argument("--timeout", type=float, default=60.0, help="seconds to wait for the response")
    parser.add_argument("--strict-json", action="store_true",
                        help="fail on non-serializable `result` instead of repr()-ing it")
    args = parser.parse_args()

    if args.ping:
        code = PING_CODE
    elif args.file:
        with open(args.file, encoding="utf-8") as fh:
            code = fh.read()
    else:
        code = args.code

    try:
        response = send(code, args.host, args.port, args.timeout, args.strict_json)
    except (ConnectionRefusedError, socket.timeout, OSError) as ex:
        print("Blender not reachable on {}:{} ({}). Is Blender open with the MCP add-on server running? "
              "It needs Preferences > System > Network > Allow Online Access.".format(args.host, args.port, ex),
              file=sys.stderr)
        return 2

    print(json.dumps(response, indent=2, ensure_ascii=False))
    return 0 if response.get("status") == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
