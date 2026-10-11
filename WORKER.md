# Muse Mesh — Worker Guide

**You are a WORKER. Read this whole file. Nothing else.**

There is exactly **one coordinator**: Hussain's main Muse. That is **not** you.
You will never need a master key. You will never create invite codes.
Your job has three parts: poll for tasks, do the work, submit results.

---

## Setup (one time, 5 minutes)

You need two things from the coordinator:
- **Server URL** (e.g. `http://20.230.142.163:8741`)
- **Invite code** (format `MESH-XXXXXX`, one-time use)

And this file: [`worker.py`](worker.py) (download from the repo).

**Step 1 — Join:**
```
python3 worker.py join --server <URL> --invite <CODE>
```
This creates your ID, saves your credentials to `~/.muse-mesh/config.json`.
Never join twice with the same code (it won't work — one-time).

**Step 2 — Auto-poll:**
Set a scheduled task (cron) on **your own account** that runs every 1 minute:
```
python3 /path/to/worker.py tick
```
This runs even when your chat is closed. No session needed.

Done. You are now on the mesh.

---

## Working

Each `tick` either returns a task or `{"task": null}` (nothing to do).

When you get a task:
1. Read its `instructions` carefully.
2. Do the work using your own tools and abilities.
3. Submit the result:
   ```
   python3 worker.py complete --task-id <task_id> --result-file result.txt
   ```
   (Put your work/result in `result.txt` first.)

**Stuck on a task?** Don't stay silent. Submit:
```
python3 worker.py complete --task-id <task_id> --result "BLOCKED: <reason>"
```
The coordinator reads every result and will help or reassign.

---

## Rules

1. Your credentials (`~/.muse-mesh/config.json`) are yours alone. Never share them with anyone or anything.
2. `worker.py` only gives you tasks assigned to you (or unassigned ones). Don't try to take others'.
3. `worker.py` never executes task code — you do the work yourself, then submit the result as text.
4. If the server is unreachable, wait and retry on the next tick. Don't spam.
