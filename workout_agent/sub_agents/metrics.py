"""The metrics agent: turns the profile into hard numbers."""

from google.adk.agents import LlmAgent

from ..config import MODEL, TARGETS_KEY
from ..tools import calculate_targets

metrics_agent = LlmAgent(
    name="metrics_agent",
    model=MODEL,
    description="Computes BMR, TDEE, calorie and protein targets from the saved profile.",
    instruction="""
You compute the numeric targets that the rest of the plan is built on.

Call `calculate_targets` immediately -- it takes no arguments and reads the
saved profile itself. Do NOT do any arithmetic yourself; the tool is the source
of truth and its numbers must be reproduced exactly.

Then write a short, plain summary containing every one of these figures:
  - BMI
  - BMR (calories burned at complete rest)
  - TDEE (maintenance calories, given their job and training)
  - Daily calorie target
  - Daily deficit
  - Daily protein target in grams
  - Expected loss per week, and weeks to reach 5 kg

If the tool returned any `notes`, repeat each one prominently -- they are safety
adjustments and must not be dropped.

Output the summary only. No workout advice, no meal advice, no preamble.
""",
    tools=[calculate_targets],
    # MECHANISM 3: the agent's final text reply is written to session state
    # under this key. That is the write half of the channel that the two
    # specialists read via {targets} in their own instructions.
    output_key=TARGETS_KEY,
)
