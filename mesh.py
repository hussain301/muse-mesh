#!/usr/bin/env python3
"""
Muse Mesh — coordinator CLI (for the coordinating Muse).

Env:  MESH_SERVER  e.g. http://127.0.0.1:8741
      MESH_MASTER  master key (or read from server dir .master_key)

Usage:
  python3 mesh.py register --name "muse-2"            -> prints muse_id + api_key (give to that Muse)
  python3 mesh.py create --title "Clip 3 banao" --instructions "..." [--assign-to muse-2]
  python3 mesh.py list                                 -> all tasks + statuses
  python3 mesh.py get <task_id>                        -> task detail + result
  python3 mesh.py muses                                -> registered muses
  python3 mesh.py status                               -> indication dashboard (liveness + delivery)
"""
import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.error

SERVER = os.environ.get("MESH_SERVER", "http://127.0.0.1:8741")
MASTER = os.environ.get("MESH_MASTER")


def call(method, path, data=None):
    global MASTER
    if not MASTER:
        # try local .master_key next to server.py
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".master_key")
        if os.path.exists(p):
            MASTER = open(p).read().strip()
    url = SERVER.rstrip("/") + path
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, method=method,
                                 headers={"Authorization": f"Bearer {MASTER}",
                                          "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        print("ERROR:", e.read().decode()[:300], file=sys.stderr)
        sys.exit(1)


def main():
    ap = argparse.ArgumentParser(description="Muse Mesh coordinator")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("register"); r.add_argument("--name", required=True)
    i = sub.add_parser("invite", help="one-time invite code for easy onboarding")
    i.add_argument("--name", required=True)
    c = sub.add_parser("create")
    c.add_argument("--title", required=True)
    c.add_argument("--instructions", required=True)
    c.add_argument("--assign-to", default=None)
    sub.add_parser("list")
    g = sub.add_parser("get"); g.add_argument("task_id")
    sub.add_parser("muses")
    sub.add_parser("status")   # indication dashboard: liveness + delivery receipts

    a = ap.parse_args()
    if a.cmd == "register":
        out = call("POST", "/v1/register", {"name": a.name})
        print(json.dumps(out, indent=2))
        print("\nGive this muse_id + api_key to that Muse instance (keep the key private).",
              file=sys.stderr)
    elif a.cmd == "invite":
        out = call("POST", "/v1/invite", {"name": a.name})
        print(json.dumps(out, indent=2))
        print("\nGive ONLY the invite_code + server URL + worker.py to the new Muse.",
              file=sys.stderr)
        print("They run: python3 worker.py join --server <URL> --invite <CODE>",
              file=sys.stderr)
    elif a.cmd == "create":
        out = call("POST", "/v1/tasks", {"title": a.title, "instructions": a.instructions,
                                         "assign_to": a.assign_to})
        print(json.dumps(out, indent=2))
    elif a.cmd == "list":
        for t in call("GET", "/v1/tasks"):
            print(f"{t['id']}  [{t['status']}]  {t['title']}  (assign: {t['assign_to'] or 'any'})")
    elif a.cmd == "get":
        print(json.dumps(call("GET", f"/v1/tasks/{a.task_id}"), indent=2, ensure_ascii=False))
    elif a.cmd == "muses":
        for m in call("GET", "/v1/muses"):
            print(f"{m['id']}  ({m['name']})")
    elif a.cmd == "status":
        # ---- indication dashboard ----
        def ago(ts):
            if not ts:
                return "kabhi nahi"
            d = int(time.time()) - int(ts)
            if d < 60:
                return f"{d}s pehle"
            if d < 3600:
                return f"{d//60} min pehle"
            return f"{d//3600}h {(d%3600)//60}min pehle"
        print("== Muses (liveness) ==")
        for m in call("GET", "/v1/muses"):
            print(f"  {m['id']}: aakhri baar active {ago(m.get('last_seen'))}")
        print("== Tasks (delivery receipts) ==")
        counts = {"pending": 0, "claimed": 0, "done": 0}
        for t in call("GET", "/v1/tasks"):
            st = t["status"]
            counts[st] = counts.get(st, 0) + 1
            if st == "claimed":
                print(f"  {t['id']}: '{t['title']}' -> {t['claimed_by']} ne utha liya ({ago(t['updated_at'])})")
            elif st == "pending":
                print(f"  {t['id']}: '{t['title']}' -> abhi tak kisi ne nahi uthaya")
        print(f"== Total: {counts.get('pending',0)} pending, {counts.get('claimed',0)} claimed, {counts.get('done',0)} done ==")


if __name__ == "__main__":
    main()
