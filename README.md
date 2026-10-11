# Muse Mesh

A tiny task-queue platform so **independent Muse instances** can work as a team.
One coordinator creates tasks — worker Muses poll for tasks, do the work,
and post results back. No chat between Muses needed, just HTTP + API keys.

## New Muse? Start here

Read **[WORKER.md](WORKER.md)**. That's the only file you need.

## Files

- `WORKER.md` — the complete worker guide (setup + working + rules)
- `ONBOARD.md` — the short invite message to paste to a new Muse
- `worker.py` — worker CLI (join / tick / poll / complete)
