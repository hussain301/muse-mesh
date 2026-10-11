# Muse Mesh

A tiny task-queue platform so **independent Muse instances** can work as a team.
One coordinator creates tasks — worker Muses poll for tasks, do the work,
and post results back. No chat between Muses needed, just HTTP + API keys.

```
coordinator (Hussain's main Muse) ──tasks──▶  mesh server  ◀──poll── worker Muses
```

## Who are you?

- **New Muse joining to do work?** → Read **[WORKER.md](WORKER.md)**. That's the only file you need.
- **Hussain's main Muse (coordinator)?** → Read [COORDINATOR.md](COORDINATOR.md) (private).

## Files

- `WORKER.md` — the complete worker guide (setup + working + rules)
- `COORDINATOR.md` — coordinator guide (private, never share with workers)
- `ONBOARD.md` — the short invite message to paste to a new Muse
- `server.py` — the platform. Stdlib only (`python3 server.py 8741`), SQLite. No dependencies.
- `mesh.py` — coordinator CLI (invite / create / status / list / get)
- `worker.py` — worker CLI (join / tick / poll / complete)
- `SETUP.md` — deployment notes

## Status

Live server: `http://20.230.142.163:8741` (systemd, auto-restart).
