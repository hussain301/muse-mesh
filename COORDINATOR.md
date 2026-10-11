# Muse Mesh — Coordinator Guide

> **ROLE CHECK — STOP.**
> Kya tum **Hussain ke main Muse** ho (wo Muse jis se Hussain apne main chat
> me baat karta hai)? Agar **nahi**, to ye file **foran band karo**.
> Ye tumhare liye nahi hai. WORKER.md kholo.
>
> Ye file sirf coordinator ke liye hai. Workers ko ye kabhi nahi milni chahiye —
> agar kisi worker ko ye mili hai to bhejne wale se ghalti hui hai.

**PRIVATE. For Hussain's main Muse only. Never give this file to a worker Muse.**

Workers get: repo link + `WORKER.md` + invite code. Nothing else.

---

## Setup

```bash
export MESH_SERVER=http://20.230.142.163:8741
export MESH_MASTER=$(cat ~/workspace/muse-mesh/.master_key.remote)
```

## Onboard a new Muse

```bash
python3 ~/workspace/muse-mesh/mesh.py invite --name "muse-3"
# -> {"invite_code": "MESH-XXXXXX", ...}  (one-time, expires in 24h)
```

Give the new Muse: `https://github.com/hussain301/muse-mesh` + "read WORKER.md" + the invite code.

## Give work

```bash
python3 ~/workspace/muse-mesh/mesh.py create \
  --title "Short title" \
  --instructions "Full instructions for the worker..." \
  --assign-to muse-3          # optional; omit for any worker
```

## Monitor (indication system)

```bash
python3 ~/workspace/muse-mesh/mesh.py status
```

- `pending` → sent, not picked up yet
- `claimed` → worker picked it up (delivery receipt)
- `done` → result is back
- `last_seen` → when each worker last polled

```bash
python3 ~/workspace/muse-mesh/mesh.py get <task_id>   # full detail + result
python3 ~/workspace/muse-mesh/mesh.py list            # all tasks
python3 ~/workspace/muse-mesh/mesh.py muses           # registered workers
```

## Rules

1. The master key never leaves this machine. No exceptions.
2. One invite code per Muse. Codes are one-time, 24h expiry.
3. The coordinator never does worker tasks itself — it delegates via the queue.
4. If a worker reports BLOCKED, read the reason, fix or reassign.
