#!/usr/bin/env python3
"""
Muse Mesh — task-queue server for coordinating independent Muse instances.

Zero dependencies (stdlib only). Run:  python3 server.py [port]
Data: mesh.db (SQLite) in the same directory.
Auth: per-Muse API keys + one master key (coordinator).

API (all JSON):
  POST /v1/register            {"name": "muse-2"}            -> {"muse_id","api_key"}   [master key]
  POST /v1/tasks               {"title","instructions","assign_to"?} -> {"task_id"}    [master key]
  GET  /v1/tasks                                          -> [tasks...]               [master key]
  GET  /v1/tasks/<id>                                     -> task detail              [master or claimer]
  GET  /v1/tasks/next?muse_id=<id>                        -> next task or {"task":null}[worker key]
  POST /v1/tasks/<id>/complete  {"result": "..."}          -> {"ok":true}              [worker key: claimer]
  GET  /v1/muses                                          -> [muses...]               [master key]
  GET  /health                                            -> {"ok":true}

Auth header:  Authorization: Bearer <api_key>
"""
import json
import os
import re
import secrets
import sqlite3
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "mesh.db")
MASTER_FILE = os.path.join(BASE, ".master_key")


def get_master_key():
    if os.environ.get("MESH_MASTER_KEY"):
        return os.environ["MESH_MASTER_KEY"]
    if os.path.exists(MASTER_FILE):
        return open(MASTER_FILE).read().strip()
    key = "mm_master_" + secrets.token_urlsafe(32)
    with open(MASTER_FILE, "w") as f:
        f.write(key)
    os.chmod(MASTER_FILE, 0o600)
    print(f"[mesh] NEW master key generated (saved to .master_key): {key}")
    return key


MASTER_KEY = get_master_key()


def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    con.execute("""CREATE TABLE IF NOT EXISTS muses(
        id TEXT PRIMARY KEY, name TEXT, api_key TEXT UNIQUE, created_at INTEGER)""")
    # invite system: easy onboarding for new muses
    con.execute("""CREATE TABLE IF NOT EXISTS invites(
        code TEXT PRIMARY KEY, name TEXT, created_at INTEGER, used INTEGER DEFAULT 0)""")
    try:
        con.execute("ALTER TABLE muses ADD COLUMN last_seen INTEGER")
    except sqlite3.OperationalError:
        pass  # column already exists
    con.execute("""CREATE TABLE IF NOT EXISTS tasks(
        id TEXT PRIMARY KEY, title TEXT, instructions TEXT, assign_to TEXT,
        status TEXT DEFAULT 'pending', claimed_by TEXT, result TEXT,
        created_at INTEGER, updated_at INTEGER)""")
    return con


def new_id(prefix):
    return f"{prefix}_{secrets.token_hex(6)}"


class Handler(BaseHTTPRequestHandler):
    server_version = "MuseMesh/0.1"

    def log_message(self, *a):
        pass  # quiet; uncomment for debugging

    # ---- helpers ----
    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        ln = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(ln) if ln else b""
        try:
            return json.loads(raw) if raw else {}
        except Exception:
            return None

    def _auth(self):
        h = self.headers.get("Authorization", "")
        m = re.match(r"Bearer\s+(\S+)", h)
        return m.group(1) if m else None

    def _touch(self, con, me):
        # indication system: record worker liveness on every poll/complete
        if me and not me.get("master"):
            con.execute("UPDATE muses SET last_seen=? WHERE id=?",
                        (int(time.time()), me["id"]))
            con.commit()

    def _muse(self, con, api_key):
        if not api_key:
            return None
        if api_key == MASTER_KEY:
            return {"id": "__coordinator__", "name": "coordinator", "master": True}
        r = con.execute("SELECT id,name FROM muses WHERE api_key=?", (api_key,)).fetchone()
        return {"id": r["id"], "name": r["name"], "master": False} if r else None

    # ---- routes ----
    def do_GET(self):
        u = urlparse(self.path)
        con = db()
        try:
            if u.path == "/health":
                return self._json(200, {"ok": True, "service": "muse-mesh"})

            me = self._muse(con, self._auth())
            if not me:
                return self._json(401, {"error": "unauthorized"})

            if u.path == "/v1/muses":
                if not me["master"]:
                    return self._json(403, {"error": "coordinator only"})
                rows = con.execute("SELECT id,name,created_at,last_seen FROM muses ORDER BY created_at").fetchall()
                return self._json(200, [dict(r) for r in rows])

            if u.path == "/v1/tasks":
                if not me["master"]:
                    return self._json(403, {"error": "coordinator only"})
                rows = con.execute("SELECT * FROM tasks ORDER BY created_at").fetchall()
                return self._json(200, [dict(r) for r in rows])

            if u.path == "/v1/tasks/next":
                qs = parse_qs(u.query)
                mid = (qs.get("muse_id") or [""])[0]
                if not mid or (not me["master"] and me["id"] != mid):
                    return self._json(403, {"error": "muse_id mismatch"})
                # oldest pending task assigned to me, else oldest unassigned
                t = con.execute(
                    """SELECT * FROM tasks WHERE status='pending'
                       AND (assign_to=? OR assign_to IS NULL OR assign_to='')
                       ORDER BY created_at LIMIT 1""", (mid,)).fetchone()
                if not t:
                    self._touch(con, me)  # poll with empty queue still proves liveness
                    return self._json(200, {"task": None})
                now = int(time.time())
                con.execute("UPDATE tasks SET status='claimed', claimed_by=?, updated_at=? WHERE id=?",
                            (mid, now, t["id"]))
                self._touch(con, me)  # delivery receipt: this muse picked up the task
                con.commit()
                t = dict(t)
                return self._json(200, {"task": {
                    "task_id": t["id"], "title": t["title"],
                    "instructions": t["instructions"], "status": "claimed"}})

            m = re.match(r"^/v1/tasks/([^/]+)$", u.path)
            if m:
                t = con.execute("SELECT * FROM tasks WHERE id=?", (m.group(1),)).fetchone()
                if not t:
                    return self._json(404, {"error": "no such task"})
                t = dict(t)
                if not me["master"] and t["claimed_by"] != me["id"]:
                    return self._json(403, {"error": "not your task"})
                t.pop("id", None)
                t["task_id"] = m.group(1)
                return self._json(200, t)

            return self._json(404, {"error": "not found"})
        finally:
            con.close()

    def do_POST(self):
        u = urlparse(self.path)
        con = db()
        try:
            data = self._body()
            if data is None:
                return self._json(400, {"error": "invalid JSON"})

            # /v1/join is public: the one-time invite code IS the auth
            if u.path == "/v1/join":
                code = (data.get("invite_code") or "").strip().upper()
                inv = con.execute("SELECT * FROM invites WHERE code=?", (code,)).fetchone()
                if not inv:
                    return self._json(404, {"error": "invalid invite code"})
                if inv["used"]:
                    return self._json(403, {"error": "invite already used"})
                if int(time.time()) - inv["created_at"] > 86400:
                    return self._json(403, {"error": "invite expired"})
                slug = re.sub(r"[^a-z0-9-]", "", inv["name"].lower().replace(" ", "-"))
                mid = slug if slug.startswith("muse-") else "muse-" + slug
                if not mid or mid == "muse-":
                    mid = new_id("muse")
                base, n = mid, 2
                while con.execute("SELECT 1 FROM muses WHERE id=?", (mid,)).fetchone():
                    mid = f"{base}-{n}"
                    n += 1
                key = "mm_" + secrets.token_urlsafe(32)
                con.execute("INSERT INTO muses(id,name,api_key,created_at) VALUES(?,?,?,?)",
                            (mid, inv["name"], key, int(time.time())))
                con.execute("UPDATE invites SET used=1 WHERE code=?", (code,))
                con.commit()
                return self._json(200, {"muse_id": mid, "api_key": key})

            me = self._muse(con, self._auth())
            if not me:
                return self._json(401, {"error": "unauthorized"})

            if u.path == "/v1/invite":
                if not me["master"]:
                    return self._json(403, {"error": "coordinator only"})
                name = (data.get("name") or "").strip()
                if not name:
                    return self._json(400, {"error": "name required"})
                code = "MESH-" + secrets.token_hex(3).upper()
                con.execute("INSERT INTO invites(code,name,created_at,used) VALUES(?,?,?,0)",
                            (code, name, int(time.time())))
                con.commit()
                return self._json(200, {"invite_code": code,
                                        "expires_in": "24h",
                                        "instructions": "Give this code to the new Muse with worker.py"})

            if u.path == "/v1/register":
                if not me["master"]:
                    return self._json(403, {"error": "coordinator only"})
                name = (data.get("name") or "").strip()
                if not name:
                    return self._json(400, {"error": "name required"})
                slug = re.sub(r"[^a-z0-9-]", "", name.lower().replace(" ", "-"))
                mid = slug if slug.startswith("muse-") else "muse-" + slug
                if not mid or mid == "muse-":
                    mid = new_id("muse")
                # ensure unique
                base, n = mid, 2
                while con.execute("SELECT 1 FROM muses WHERE id=?", (mid,)).fetchone():
                    mid = f"{base}-{n}"
                    n += 1
                key = "mm_" + secrets.token_urlsafe(32)
                con.execute("INSERT INTO muses(id,name,api_key,created_at) VALUES(?,?,?,?)",
                            (mid, name, key, int(time.time())))
                con.commit()
                return self._json(200, {"muse_id": mid, "api_key": key})

            if u.path == "/v1/tasks":
                if not me["master"]:
                    return self._json(403, {"error": "coordinator only"})
                title = (data.get("title") or "").strip()
                instructions = (data.get("instructions") or "").strip()
                if not title or not instructions:
                    return self._json(400, {"error": "title and instructions required"})
                assign_to = (data.get("assign_to") or "").strip() or None
                if assign_to and not con.execute("SELECT 1 FROM muses WHERE id=?", (assign_to,)).fetchone():
                    return self._json(400, {"error": "unknown muse_id"})
                tid = new_id("task")
                now = int(time.time())
                con.execute(
                    "INSERT INTO tasks(id,title,instructions,assign_to,status,created_at,updated_at)"
                    " VALUES(?,?,?,?, 'pending',?,?)",
                    (tid, title, instructions, assign_to, now, now))
                con.commit()
                return self._json(200, {"task_id": tid})

            m = re.match(r"^/v1/tasks/([^/]+)/complete$", u.path)
            if m:
                tid = m.group(1)
                t = con.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()
                if not t:
                    return self._json(404, {"error": "no such task"})
                if t["claimed_by"] != me["id"] and not me["master"]:
                    return self._json(403, {"error": "task not claimed by you"})
                result = data.get("result", "")
                con.execute("UPDATE tasks SET status='done', result=?, updated_at=? WHERE id=?",
                            (str(result), int(time.time()), tid))
                self._touch(con, me)
                con.commit()
                return self._json(200, {"ok": True})

            return self._json(404, {"error": "not found"})
        finally:
            con.close()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8741
    print(f"[mesh] Muse Mesh server on port {port}  (db: {DB})")
    print(f"[mesh] Master key: {MASTER_KEY[:12]}... (full key in .master_key)")
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()
