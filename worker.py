#!/usr/bin/env python3
"""
Muse Mesh — worker CLI for an independent Muse instance.

EASY ONBOARDING (new muse):
  1. Coordinator gives you: SERVER_URL + INVITE_CODE (+ this file)
  2. Run:  python3 worker.py join --server URL --invite MESH-XXXXXX
     -> saves your credentials to ~/.muse-mesh/config.json
  3. Set a cron on your account (every 1 min) that runs:
        python3 /path/to/worker.py tick
     (tick = poll + auto-report; you do the work when a task arrives)

Manual usage (credentials from config file or flags):
  python3 worker.py poll [--server URL --muse-id ID --api-key KEY]
  python3 worker.py complete --task-id ID (--result "..." | --result-file f)
  python3 worker.py tick        # poll once; prints task or {"task": null}
"""
import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.error

CONFIG = os.path.expanduser("~/.muse-mesh/config.json")


def load_config():
    if os.path.exists(CONFIG):
        try:
            return json.load(open(CONFIG))
        except Exception:
            return {}
    return {}


def save_config(cfg):
    os.makedirs(os.path.dirname(CONFIG), exist_ok=True)
    with open(CONFIG, "w") as f:
        json.dump(cfg, f, indent=2)
    os.chmod(CONFIG, 0o600)


def call(server, method, path, api_key=None, data=None, retries=3):
    url = server.rstrip("/") + path
    body = json.dumps(data).encode() if data is not None else None
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=body, method=method, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            try:
                detail = json.loads(e.read().decode())
            except Exception:
                detail = {"error": f"http_{e.code}"}
            print(json.dumps({"error": detail}, indent=2))
            sys.exit(1)
        except Exception as e:
            # transient network/proxy truncation (IncompleteRead,
            # RemoteDisconnected, timeouts) -> retry with backoff
            if attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
                continue
            print(json.dumps(
                {"error": f"connection failed after {retries} tries: {type(e).__name__}"},
                indent=2))
            sys.exit(1)


def resolve(args):
    """Fill server/muse_id/api_key from flags or saved config."""
    cfg = load_config()
    server = args.server or cfg.get("server")
    muse_id = getattr(args, "muse_id", None) or cfg.get("muse_id")
    api_key = getattr(args, "api_key", None) or cfg.get("api_key")
    if not server or not muse_id or not api_key:
        print("ERROR: server/muse_id/api_key missing. Run 'worker.py join' first, "
              "or pass --server/--muse-id/--api-key.", file=sys.stderr)
        sys.exit(1)
    return server, muse_id, api_key


def main():
    ap = argparse.ArgumentParser(description="Muse Mesh worker")
    sub = ap.add_subparsers(dest="cmd", required=True)

    j = sub.add_parser("join", help="one-time onboarding with an invite code")
    j.add_argument("--server", required=True, help="e.g. http://20.230.142.163:8741")
    j.add_argument("--invite", required=True, help="e.g. MESH-A1B2C3")

    p = sub.add_parser("poll")
    p.add_argument("--server", default=None)
    p.add_argument("--muse-id", default=None)
    p.add_argument("--api-key", default=None)

    t = sub.add_parser("tick", help="poll once using saved config (for cron)")
    t.add_argument("--server", default=None)
    t.add_argument("--muse-id", default=None)
    t.add_argument("--api-key", default=None)

    c = sub.add_parser("complete")
    c.add_argument("--server", default=None)
    c.add_argument("--api-key", default=None)
    c.add_argument("--task-id", required=True)
    g = c.add_mutually_exclusive_group(required=True)
    g.add_argument("--result", default=None)
    g.add_argument("--result-file", default=None)

    s = sub.add_parser("send", help="private message to coordinator (not a task)")
    s.add_argument("--server", default=None)
    s.add_argument("--api-key", default=None)
    s.add_argument("--text", required=True)

    r = sub.add_parser("read", help="read coordinator replies to you")
    r.add_argument("--server", default=None)
    r.add_argument("--api-key", default=None)

    a = ap.parse_args()

    if a.cmd == "join":
        out = call(a.server, "POST", "/v1/join", None,
                   {"invite_code": a.invite})
        save_config({"server": a.server.rstrip("/"),
                     "muse_id": out["muse_id"],
                     "api_key": out["api_key"]})
        print(f"Joined as {out['muse_id']}. Credentials saved to {CONFIG}")
        print("Next: set a cron (every 1 min) on your account that runs:")
        print(f"  python3 {os.path.abspath(__file__)} tick")
        print("When a task arrives, do the work, then:")
        print(f"  python3 {os.path.abspath(__file__)} complete --task-id <id> --result-file result.txt")

    elif a.cmd in ("poll", "tick"):
        server, muse_id, api_key = resolve(a)
        out = call(server, "GET", f"/v1/tasks/next?muse_id={muse_id}", api_key)
        print(json.dumps(out, indent=2, ensure_ascii=False))

    elif a.cmd == "complete":
        server, _, api_key = resolve(a)
        result = a.result
        if a.result_file:
            result = open(a.result_file, encoding="utf-8").read()
        out = call(server, "POST", f"/v1/tasks/{a.task_id}/complete",
                   api_key, {"result": result})
        print(json.dumps(out, indent=2))

    elif a.cmd == "send":
        server, _, api_key = resolve(a)
        out = call(server, "POST", "/v1/messages", api_key, {"text": a.text})
        print(json.dumps(out, indent=2))

    elif a.cmd == "read":
        server, muse_id, api_key = resolve(a)
        # limit=10 keeps the payload small; large responses get truncated
        # by some proxies (IncompleteRead). call() also retries transient
        # connection errors automatically.
        msgs = call(server, "GET", "/v1/messages?limit=10", api_key)
        mine = [m for m in msgs if m.get("to_muse") in (muse_id, None, "")]
        if not mine:
            print("(coordinator se koi jawab nahi)")
        for m in mine:
            print(f"[{m['from_muse']}]: {m['text']}\n")


if __name__ == "__main__":
    main()
