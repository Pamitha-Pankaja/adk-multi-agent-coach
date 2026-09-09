# Deploying the coach

The whole app is one container: `serve_ui.py` serves the chat UI and runs the agents
in-process. Anywhere that runs a container and sets `$PORT` will work — the instructions
below use Fly.io, with Railway and Render noted at the end.

**Fly is the easy path here** because it builds remotely (you don't need Docker installed)
and deploys from this directory (you don't need to push to GitHub first).

---

## Before you start

You need a Gemini API key. The one in `workout_agent/.env` works — you'll copy its value
into Fly's secret store rather than into the image. `.dockerignore` keeps `.env` out of the
build, so the key is never baked into the container.

**Set a spending cap first.** The app is going up with no login, so anyone with the URL can
generate plans on your key — roughly 12 model calls each. Go to
[aistudio.google.com](https://aistudio.google.com/apikey) → your key → the linked Cloud
project → **Billing → Budgets & alerts**, and set a cap you're comfortable with. Do this
before you share the link, not after.

---

## Deploy to Fly.io

```bash
brew install flyctl          # once
fly auth signup              # or: fly auth login
```

From this directory:

```bash
# 1. Create the app.
#    `fly launch` REGENERATES fly.toml even if you decline the prompt, dropping
#    [env] and max_machines_running. After it runs, check fly.toml still has
#    both — see "What fly.toml must contain" below.
fly launch --no-deploy

# 2. Give it the API key (never goes in the image or in git)
fly secrets set GOOGLE_API_KEY="$(grep '^GOOGLE_API_KEY=' workout_agent/.env | cut -d= -f2-)"

# 3. Ship it — builds on Fly's builders, so no local Docker needed
fly deploy --remote-only

# 4. Open it
fly open
```

Check on it with `fly logs`, `fly status`, and `fly apps destroy workout-coach` to remove it
entirely.

### If you get a 502

Check the deploy output for:

```
WARNING The app is not listening on the expected address
PROCESS             ADDRESSES
python serve_ui.py  127.0.0.1:8080
```

That means the app bound localhost inside the container, so fly-proxy can't reach
it. `serve_ui.py` binds `0.0.0.0` by default now, so this should not recur — but if
you ever set `HOST=127.0.0.1`, that's the cause.

Also check machine count. `fly launch` defaults to two for high availability, which
breaks in-memory sessions:

```bash
fly scale count 1
fly status              # confirm exactly one machine
fly logs                # live logs
```

### What `fly.toml` must contain

| Setting | Why |
|---|---|
| `auto_stop_machines = "stop"` | Scales to zero when idle, so an unused app costs nothing. |
| `min_machines_running = 0` | Same — nothing runs until someone opens the URL. |
| `max_machines_running = 1` | **Important.** Sessions live in memory, so a person's second message must reach the same machine as their first. |
| `force_https = true` | The chat streams over SSE; keep it on TLS. |
| `primary_region = "sin"` | Singapore. `fly platform regions` lists the rest. |

First request after idle takes a few seconds while the machine wakes.

---

## Railway or Render instead

Both build from a GitHub repo, so **push first** — they can't see your working directory.
Your repo is private; both can read private repos once you authorise them.

1. New project → deploy from `Pamitha-Pankaja/adk-multi-agent-coach`
2. They auto-detect the `Dockerfile`; no build command needed
3. Add an environment variable `GOOGLE_API_KEY` with your key
4. Set instances/replicas to **1**, for the in-memory session reason above

Render's free web services sleep after inactivity and can take ~50s to wake — fine for a
demo, annoying to show someone live. Railway has no free tier now but doesn't sleep.

---

## Things to know before it's public

**Sessions are in memory.** A redeploy or a scale-to-zero wake drops every in-flight
conversation — someone mid-intake starts over. That's why it's pinned to one machine. To
make conversations survive restarts, swap `InMemorySessionService` in `serve_ui.py` for
`DatabaseSessionService` (`pip install "google-adk[db]"`, then point it at a Postgres URL)
and you can raise the machine count too.

**There's no login.** Anyone with the URL can use it. The spending cap above is your real
protection. If you later want a door on it, the smallest useful version is a shared
password checked in a FastAPI dependency on `/api/*`.

**It gives dietary and exercise advice.** The safety floors in `tools.py` and the
`safety_reviewer` agent are what keep the numbers sane, and every plan carries the
not-medical-advice line. Keep all three if you change anything in that path.

**Cost.** One complete plan is ~12 Gemini calls on `gemini-flash-latest`. Idle hosting on
Fly is free; you're really only paying for model usage.

---

## Updating it

```bash
fly deploy --remote-only
```

Nothing else to do — the image rebuilds from this directory each time.
