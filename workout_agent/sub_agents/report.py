"""The fan-in step: one agent assembles everything, with a safety check.

LEARNING NOTE -- AgentTool vs. sub_agents, the distinction worth internalising:

  sub_agents=[x]        the model can emit transfer_to_agent(x). Control moves
                        to x and does NOT come back. x now owns the conversation.
                        Use it for routing: "this request belongs to someone else."

  tools=[AgentTool(x)]  x is called like a function. It runs, returns a string,
                        and the CALLER resumes with that string in hand.
                        Use it for consultation: "I need an answer from x, then
                        I will carry on."

safety_reviewer is a consultation -- report_agent needs its verdict in order to
write the final document, so a one-way transfer would be exactly wrong. Swap the
two and you can watch the report never get written; that experiment is in the
README.
"""

from google.adk.agents import LlmAgent
from google.adk.tools import AgentTool

from ..config import MODEL, REPORT_KEY

safety_reviewer = LlmAgent(
    name="safety_reviewer",
    model=MODEL,
    description=(
        "Reviews a proposed weight-loss plan for safety problems and returns a "
        "short verdict. Call this before presenting any plan to the user."
    ),
    instruction="""
You are a conservative safety reviewer. You will be given a person's profile,
their computed targets, and the plans proposed for them.

Check for:
  - A loss rate above 1 kg per week.
  - A calorie target below 1500 (male) or 1200 (female).
  - A BMI already below 20, where losing 5 kg may be inappropriate.
  - Any medical condition, injury, pregnancy, or eating-disorder history
    mentioned in the profile that the plans have ignored.
  - Exercise prescriptions that conflict with a stated injury.
  - Anyone under 18 or over 65, where generic plans need more caution.

Reply in this form and nothing else:

VERDICT: SAFE  (or: CAUTION, or: UNSAFE)
CONCERNS:
- one line per concern, or "none" if there are none
ADVICE: one or two sentences the coach should pass on to the user.

Be direct. If nothing is wrong, say so plainly -- do not manufacture concerns.
""",
)

report_agent = LlmAgent(
    name="report_agent",
    model=MODEL,
    description="Assembles the final plan document from the specialists' output.",
    # All four keys are read here. This is the fan-in: two parallel branches
    # wrote to state, and this agent is the first place they meet.
    instruction="""
You are the head coach. Assemble the final document the user takes away.

Profile:
{profile}

Targets:
{targets}

Proposed training programme:
{workout_plan}

Proposed nutrition plan:
{meal_plan}

Step 1 -- before writing anything, call the `safety_reviewer` tool. Pass it the
profile, the targets, and a condensed version of both plans. Wait for its verdict.

Step 2 -- write the final document in markdown:

  # Your 5 kg Plan
  A two or three sentence overview: where they are now, the daily calorie and
  protein target, and roughly how many weeks this should take.

  ## Your Numbers
  A small table: BMI, BMR, maintenance calories, daily target, daily deficit,
  protein target, expected weekly loss, weeks to goal. Use the figures from
  Targets above verbatim -- do not recompute anything.

  ## Training
  The programme, tidied up.

  ## Nutrition
  The eating plan, tidied up.

  ## Staying On Track
  Three or four things that actually determine whether this works.

  ## Before You Start
  Anything the safety reviewer raised, stated plainly. If the verdict was
  CAUTION or UNSAFE, put it here in bold and do not bury it. Then close with:
  "This is general guidance, not medical advice. Check with a doctor or a
  registered dietitian before starting, especially if you have any medical
  condition."

Keep the user's own details visible throughout -- this should read as written
for them, not as a template.
""",
    # MECHANISM 6: an agent exposed as a callable tool.
    tools=[AgentTool(agent=safety_reviewer)],
    output_key=REPORT_KEY,
)
