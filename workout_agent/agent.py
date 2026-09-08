"""Wiring only. No logic lives here -- this is the map of the system.

    root_agent = coach                LlmAgent      <- decides where to go
    |
    +-- intake_agent                  LlmAgent      <- asks the questions
    |     tools=[save_profile]                         writes state["profile"]
    |
    +-- plan_pipeline                 SequentialAgent  <- fixed order
          |
          +-- metrics_agent           LlmAgent      -> state["targets"]
          |     tools=[calculate_targets]
          |
          +-- specialists             ParallelAgent <- fan-out, concurrent
          |     +-- workout_designer  -> state["workout_plan"]
          |     +-- meal_designer     -> state["meal_plan"]
          |
          +-- report_agent            LlmAgent      -> state["final_plan"]
                tools=[AgentTool(safety_reviewer)]  <- consults, then resumes
"""

from google.adk.agents import LlmAgent, SequentialAgent

from .config import MODEL
from .sub_agents.intake import intake_agent
from .sub_agents.metrics import metrics_agent
from .sub_agents.report import report_agent
from .sub_agents.specialists import specialists

# MECHANISM 5b: deterministic sequencing. SequentialAgent is not an LLM -- it
# just runs its children in list order, every time. Compare this with the coach
# below, where a model chooses. Knowing which of the two you want is most of
# multi-agent design: use a workflow agent when the order is known in advance,
# and an LLM router only when it genuinely depends on what the user said.
plan_pipeline = SequentialAgent(
    name="plan_pipeline",
    description=(
        "Builds the complete 5 kg plan: computes targets, then designs the "
        "training and nutrition plans, then assembles the final document. "
        "Requires that a profile has already been saved."
    ),
    sub_agents=[metrics_agent, specialists, report_agent],
)

# MECHANISM 1: LLM-driven delegation. Because these are `sub_agents`, ADK gives
# this agent a `transfer_to_agent` tool automatically and shows the model each
# child's `description`. The model picks. Nothing here is hard-coded.
#
# Note `{profile?}` -- the trailing `?` makes the placeholder optional. On the
# very first turn no profile exists, and a bare {profile} would raise KeyError
# before the model was ever called.
root_agent = LlmAgent(
    name="coach",
    model=MODEL,
    description="Front desk for a weight-loss coaching service.",
    instruction="""
You are the front desk. You route people. You never ask profile questions
yourself and you never write plans yourself.

The profile on file right now (empty means none has been collected):
{profile?}

Routing:
- No profile yet -> transfer to `intake_agent` IMMEDIATELY. Say at most one
  short line first, like "Happy to help -- a few quick questions." Do not list
  what you are about to ask. Do not explain the process.
- Profile exists, they want their plan -> transfer to `plan_pipeline`.
- Profile exists, they want to change a detail -> transfer to `intake_agent`.
- They are just asking what you do -> answer in one sentence.

Never end your turn without either transferring or answering a direct question.
Never ask permission to continue.
""",
    sub_agents=[intake_agent, plan_pipeline],
)
