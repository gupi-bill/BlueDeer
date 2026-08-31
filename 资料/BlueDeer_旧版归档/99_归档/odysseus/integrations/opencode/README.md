# Odysseus OpenCode Integration

This directory contains the OpenCode skill bundle for Odysseus.

OpenCode (opencode.ai) is a terminal coding agent in the same family as Claude
Code and Codex. At runtime it calls the **shared, scope-gated** Odysseus agent
API under `/api/codex/*` — the `codex` path is a historic name shared by every
agent integration, so OpenCode needs no separate backend surface. What this
bundle adds is the OpenCode-side skill + a helper so OpenCode knows how to reach
Odysseus, plus a UI entry point so you can mint a scoped **OpenCode Agent** token
from Odysseus Settings.

## User Flow

1. Open Odysseus Settings > Integrations.
2. Click **+ Add Integration** and pick **OpenCode Agent**.
3. Name the agent, then copy the full setup commands shown after the token is generated.
4. Toggle the Odysseus tools OpenCode is allowed to use (todos, email, memory, calendar, documents, cookbook).
5. Paste the setup commands into your terminal (OpenCode's machine):

```bash
export ODYSSEUS_URL=http://your-odysseus-host:7000
export ODYSSEUS_API_TOKEN=ody_generated_token
mkdir -p ~/.config/opencode/skills
curl -fsSL -H "Authorization: Bearer $ODYSSEUS_API_TOKEN" "$ODYSSEUS_URL/api/opencode/plugin.zip" -o /tmp/odysseus-opencode-skill.zip
python3 -m zipfile -e /tmp/odysseus-opencode-skill.zip ~/.config/opencode/skills/
python3 ~/.config/opencode/skills/odysseus/scripts/odysseus_api.py capabilities
```

OpenCode auto-loads any `SKILL.md` under its skills directory, so the `odysseus`
skill is available whenever OpenCode starts with `ODYSSEUS_URL` and
`ODYSSEUS_API_TOKEN` in its environment.

> **Windows note:** the commands above are POSIX shell. On Windows run them from
> Git Bash (already present on this machine) or WSL. If your OpenCode install
> uses a different skills path, drop `skills/odysseus/` there manually and point
> the helper at its `scripts/odysseus_api.py`.

## What's in the bundle

- `skills/odysseus/SKILL.md` — the skill definition OpenCode reads.
- `skills/odysseus/scripts/odysseus_api.py` — small helper that calls the scoped
  `/api/codex/*` endpoints (the canonical scope-gated agent API shared by all
  agent integrations).

## Scope enforcement

The token is scope-gated. Every tool surface is checked server-side in Odysseus,
so even if OpenCode tries to call a forbidden endpoint, it gets `403` until you
enable the matching toggle in Settings > Integrations > OpenCode Agent.
