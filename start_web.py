"""Open a dev-UI session that already has the agent's greeting in it.

WHY THIS EXISTS

`adk web`'s "New Session" button creates an empty session and waits for you to
type. ADK has no welcome-message setting, so the agent cannot open the
conversation by itself.

But the dev server's REST API *can* create a session with events already in it.
So this script:

  1. generates a real greeting by running the agent against a hidden kickoff turn
     (see greeting.py -- the text is model-generated, not hardcoded),
  2. creates a fresh session on the running dev server with that greeting
     already appended,
  3. prints the URL.

Open it and the first thing you see is the agent's greeting and its first
question. Answer it and the conversation continues normally.

Requires `adk web .` to already be running.

Usage:  .venv/bin/python start_web.py [--port 8000]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / "workout_agent" / ".env")

from google.adk.runners import Runner              # noqa: E402
from google.adk.sessions import InMemorySessionService  # noqa: E402

from workout_agent.agent import root_agent         # noqa: E402
from workout_agent.greeting import generate_opening  # noqa: E402

APP_NAME = "workout_agent"
USER_ID = "user"


async def make_greeting() -> str:
    """Run the agent locally just to produce its opening line."""
    svc = InMemorySessionService()
    runner = Runner(app_name="greeting", agent=root_agent, session_service=svc)
    await svc.create_session(app_name="greeting", user_id="u", session_id="s")
    return await generate_opening(runner, "u", "s")


def create_seeded_session(base: str, greeting: str) -> str:
    """POST a new session to the dev server with the greeting already in it."""
    session_id = str(uuid.uuid4())
    payload = {
        "session_id": session_id,
        "events": [
            {
                # Authored by the root agent, so the dev UI renders it as the
                # agent speaking. No `actions` -- the server rejects seeded
                # events that claim to be ADK-generated control events.
                "author": root_agent.name,
                "content": {"role": "model", "parts": [{"text": greeting}]},
            }
        ],
    }
    req = urllib.request.Request(
        f"{base}/apps/{APP_NAME}/users/{USER_ID}/sessions",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())["id"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()
    base = f"http://127.0.0.1:{args.port}"

    try:
        urllib.request.urlopen(f"{base}/list-apps", timeout=10).read()
    except Exception:
        raise SystemExit(
            f"No dev server on {base}.\n"
            f"Start one first:  .venv/bin/adk web . --port {args.port}"
        )

    print("Generating the greeting...")
    greeting = asyncio.run(make_greeting())
    session_id = create_seeded_session(base, greeting)

    print(f"\n  {greeting}\n")
    print("Open this and just answer:\n")
    print(f"  {base}/dev-ui/?app={APP_NAME}&userId={USER_ID}&session={session_id}\n")


if __name__ == "__main__":
    main()
