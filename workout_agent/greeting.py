"""Producing the agent's opening message.

ADK has no "welcome message" setting: a Runner only runs when it is given a
user message, so an agent cannot speak first on its own. The workaround is a
KICKOFF -- one synthetic user turn that the human never sees. The agent
responds to it with a real, model-generated greeting, and that response is the
first thing on screen.

`run_cli.py` does this inline. `start_web.py` does it against the dev-UI server
and seeds the result into a fresh session, because the dev UI's own "New
Session" button cannot.
"""

from __future__ import annotations

# Phrased as a user asking for help, so the coach routes to intake_agent and
# intake_agent opens with its greeting. Never displayed.
KICKOFF = "I want to lose 5 kg. Greet me and ask your first question."


async def generate_opening(runner, user_id: str, session_id: str) -> str:
    """Run the kickoff turn and return the agent's generated greeting text."""
    from google.genai import types

    chunks: list[str] = []
    async for event in runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=types.Content(role="user", parts=[types.Part(text=KICKOFF)]),
    ):
        if event.content and event.content.parts and not event.partial:
            text = "".join(p.text or "" for p in event.content.parts).strip()
            if text:
                chunks.append(text)
    return "\n\n".join(chunks)
