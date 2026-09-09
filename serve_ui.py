"""A small chat UI for the coach.

`adk web` is a debugger -- it shows you events, traces and state, which is what
you want while learning. This is the other half: what a real front end looks
like when you put one on an ADK agent.

It owns the Runner directly rather than talking to the dev server, so it is the
whole stack in one file:

    browser  --POST /api/chat-->  Runner.run_async()  --stream-->  browser

Each ADK event is forwarded to the browser as one server-sent-event line, so
the page can show agents lighting up as they run instead of freezing for a
minute while the pipeline works.

Run:  .venv/bin/python serve_ui.py     then open http://localhost:8080
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / "workout_agent" / ".env")

import uvicorn                                        # noqa: E402
from fastapi import FastAPI                           # noqa: E402
from fastapi.responses import HTMLResponse, StreamingResponse  # noqa: E402
from google.adk.runners import Runner                 # noqa: E402
from google.adk.sessions import InMemorySessionService  # noqa: E402
from google.genai import types                        # noqa: E402
from pydantic import BaseModel                        # noqa: E402

from workout_agent.agent import root_agent            # noqa: E402
from workout_agent.greeting import KICKOFF            # noqa: E402

APP_NAME = "workout_coach_ui"
UI_FILE = Path(__file__).parent / "ui" / "index.html"

app = FastAPI(title="Weight-loss coach")
session_service = InMemorySessionService()
runner = Runner(app_name=APP_NAME, agent=root_agent, session_service=session_service)


class ChatRequest(BaseModel):
    session_id: str
    text: str


def sse(payload: dict) -> str:
    """Format one dict as a server-sent event."""
    return f"data: {json.dumps(payload)}\n\n"


async def stream_turn(session_id: str, text: str):
    """Run one turn and yield each ADK event as it happens."""
    user_id = session_id  # one user per browser session, good enough for local use

    try:
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=types.Content(role="user", parts=[types.Part(text=text)]),
        ):
            author = event.author

            # A transfer is the visible moment one agent hands to another.
            for call in event.get_function_calls() or []:
                if call.name == "transfer_to_agent":
                    yield sse({
                        "type": "transfer",
                        "author": author,
                        "target": (call.args or {}).get("agent_name"),
                    })
                else:
                    yield sse({"type": "tool", "author": author, "tool": call.name})

            for resp in event.get_function_responses() or []:
                yield sse({"type": "tool_done", "author": author, "tool": resp.name})

            # State writes: this is agent-to-agent communication, made visible.
            delta = (event.actions.state_delta or {}) if event.actions else {}
            for key in delta:
                if not key.startswith("_"):
                    yield sse({"type": "state", "author": author, "key": key})

            if event.content and event.content.parts and not event.partial:
                body = "".join(p.text or "" for p in event.content.parts).strip()
                if body:
                    yield sse({"type": "message", "author": author, "text": body})

    except Exception as exc:  # surface failures in the UI instead of hanging
        yield sse({"type": "error", "text": f"{type(exc).__name__}: {exc}"})

    yield sse({"type": "done"})


@app.get("/healthz")
async def healthz() -> dict:
    """Liveness probe. Hosting platforms poll this to decide if the app is up."""
    return {"ok": True}


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    return UI_FILE.read_text()


@app.post("/api/session")
async def new_session():
    """Start a session and let the agent speak first.

    Same kickoff trick as the CLI: one synthetic user turn the browser never
    renders, whose reply becomes the opening greeting on screen.
    """
    session_id = str(uuid.uuid4())
    await session_service.create_session(
        app_name=APP_NAME, user_id=session_id, session_id=session_id
    )

    greeting_parts: list[str] = []
    async for event in runner.run_async(
        user_id=session_id,
        session_id=session_id,
        new_message=types.Content(role="user", parts=[types.Part(text=KICKOFF)]),
    ):
        if event.content and event.content.parts and not event.partial:
            body = "".join(p.text or "" for p in event.content.parts).strip()
            if body:
                greeting_parts.append(body)

    return {"session_id": session_id, "greeting": "\n\n".join(greeting_parts)}


@app.post("/api/chat")
async def chat(req: ChatRequest):
    return StreamingResponse(
        stream_turn(req.session_id, req.text),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


if __name__ == "__main__":
    # Bind 0.0.0.0 always. Inside a container, listening on 127.0.0.1 means the
    # host's proxy cannot reach the app and every request returns 502 -- and you
    # cannot reliably detect "am I in a container?" from the environment, so
    # don't try. Override with HOST=127.0.0.1 if you want local-only.
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8080"))

    if not os.environ.get("GOOGLE_API_KEY"):
        raise SystemExit(
            "GOOGLE_API_KEY is not set.\n"
            "  Locally:  put it in workout_agent/.env\n"
            "  Deployed: set it as a secret, e.g. fly secrets set GOOGLE_API_KEY=..."
        )

    print(f"\n  Weight-loss coach UI  ->  http://{host}:{port}\n")
    uvicorn.run(app, host=host, port=port, log_level="warning")
