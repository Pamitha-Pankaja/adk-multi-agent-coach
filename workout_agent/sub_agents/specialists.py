"""The two specialists, and the ParallelAgent that fans out to them.

LEARNING NOTE -- why these two run in parallel:

The workout plan and the meal plan both depend only on {profile} and {targets},
and neither depends on the other. That independence is the entire precondition
for parallelism, and it is what makes ParallelAgent the right tool here rather
than decoration.

The subtle part: ParallelAgent gives each branch its own *conversation history*
(internally it copies the invocation context and sets a distinct `branch`), so
the meal designer never sees the workout designer's reasoning. But both branches
share one *session state* object. That is why both can read the same {targets},
and why both of their output_key writes survive. Isolated history, shared state.
"""

from google.adk.agents import LlmAgent, ParallelAgent

from ..config import MEAL_KEY, MODEL, WORKOUT_KEY

# MECHANISM 4: {profile} and {targets} are substituted from session state before
# the model is called. This is the actual agent-to-agent data channel -- the
# metrics agent never "sends" anything, it just writes state that these read.
#
# Note {targets} has no `?`. That is deliberate: if metrics_agent somehow did not
# run, we want a loud KeyError rather than a plan quietly built on nothing.
# Use {key?} only where a key is genuinely optional.

workout_designer = LlmAgent(
    name="workout_designer",
    model=MODEL,
    description="Designs the training programme.",
    instruction="""
You are a strength and conditioning coach. Design a training programme for this
person, whose goal is to lose 5 kg.

Their profile:
{profile}

Their computed targets:
{targets}

Produce:
1. A weekly schedule, day by day, that fits the training level in their profile.
   Do not jump someone who trains zero times a week straight to six days.
2. For each session: the exercises, sets, reps, and rest. Include both resistance
   work (it preserves muscle in a deficit) and cardio.
3. A short progression note -- how the programme should change around weeks 4-6.
4. Anything they should avoid, based on the injuries field. Take this seriously;
   if they listed a knee problem, do not prescribe deep squats and lunges.
5. Practical notes for their specific job. A desk worker and a construction
   worker need different advice about recovery and daily movement.

Be specific and concrete. Markdown, with headings. Output the programme only --
no preamble, no meal advice.
""",
    output_key=WORKOUT_KEY,
)

meal_designer = LlmAgent(
    name="meal_designer",
    model=MODEL,
    description="Designs the nutrition plan.",
    instruction="""
You are a nutrition coach. Design an eating plan for this person, whose goal is
to lose 5 kg.

Their profile:
{profile}

Their computed targets:
{targets}

Produce:
1. The daily calorie and protein target, restated exactly as given above.
   Do not recalculate them.
2. A full day of example meals -- breakfast, lunch, dinner, two snacks -- with
   rough calories per meal, adding up to close to the daily target.
3. A second, different example day, so they are not eating the same thing daily.
4. A short list of staple foods to keep in, suited to their dietary preference.
5. Three or four practical habits that matter more than the specific menu
   (protein at every meal, water, how to handle eating out).

Every suggestion must respect their dietary preference -- if they are
vegetarian, no meat appears anywhere.

Be specific and concrete. Markdown, with headings. Output the plan only --
no preamble, no workout advice.
""",
    output_key=MEAL_KEY,
)

# MECHANISM 5a: fan-out. No LLM decides this -- ParallelAgent just runs both,
# concurrently, every time.
specialists = ParallelAgent(
    name="specialists",
    description="Runs the workout designer and the meal designer concurrently.",
    sub_agents=[workout_designer, meal_designer],
)
