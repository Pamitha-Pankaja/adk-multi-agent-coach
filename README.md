# Weight-Loss Coach — a multi-agent ADK project

A team of seven agents that interviews you, computes your calorie targets, designs a
training programme and a meal plan in parallel, safety-checks the result, and hands you a
document.

It works, but the plan is the vehicle — the point is to make **every way ADK agents talk to
each other** visible in one small codebase you can read in a sitting.

```
                          ┌─────────┐
      you ───────────────▶│  coach  │  LlmAgent — decides where you go
                          └────┬────┘
              ┌────────────────┴────────────────┐
              ▼                                 ▼
      ┌───────────────┐                ┌──────────────────┐
      │ intake_agent  │                │  plan_pipeline   │ SequentialAgent
      │  asks you     │                └────────┬─────────┘
      │  9 questions  │                         │ (fixed order)
      └───────┬───────┘             ┌───────────┼───────────┐
              │                     ▼           ▼           ▼
        save_profile         ┌───────────┐  ┌────────┐  ┌────────────┐
              │              │  metrics  │  │ speci- │  │   report   │
              ▼              │  _agent   │  │ alists │  │   _agent   │
    state["profile"] ───────▶│           │  │        │  │            │
                             │ calculate │  │  ┌─────┴──┴────┐       │
                             │ _targets  │  │  │  workout    │       │
                             └─────┬─────┘  │  │  _designer  │──┐    │
                                   │        │  ├─────────────┤  │    │
                        state["targets"] ───┼─▶│  meal       │──┤    │
                                            │  │  _designer  │  │    │
                                            │  └─────────────┘  │    │
                                            └───ParallelAgent───┘    │
                                                                     │
                              state["workout_plan"], ["meal_plan"] ──┘
                                                       │
                                                       ▼
                                              ┌─────────────────┐
                                              │ safety_reviewer │ ◀── AgentTool
                                              └─────────────────┘     (returns!)
                                                       │
                                              state["final_plan"]
```

---

## Setup

```bash
uv venv
uv pip install -r requirements.txt
cp .env.example workout_agent/.env      # then paste your key in
```

Get a key at [aistudio.google.com/apikey](https://aistudio.google.com/apikey). The `.env`
belongs **inside** `workout_agent/`, and it is gitignored.

## Run it

```bash
.venv/bin/adk web .                  # dev UI at localhost:8000  ← start here
.venv/bin/python start_web.py        # ...then this, for a greeting already waiting
.venv/bin/python run_cli.py          # raw event stream in the terminal
.venv/bin/python test_tools.py       # the deterministic tests
```

The agent opens the conversation and asks **one short question at a time**, adapting each
one to what you just said — tell it you're a nurse and it asks about your shifts, not from
a generic list. Give it several facts at once and it skips ahead. After the last answer it
saves your profile and builds the plan itself; you never have to ask.

The **Events** tab shows every transfer and tool call; the **State** tab shows the five
keys filling in.

### Getting the agent to speak first

ADK has no welcome-message setting. A `Runner` only runs when handed a user message, so an
agent cannot open a conversation on its own. The workaround is a **kickoff**: one synthetic
user turn you never see, which the agent answers with a real generated greeting. That lives
in [`greeting.py`](workout_agent/greeting.py).

`run_cli.py` does it inline. For the dev UI it needs a second step, because the "New
Session" button always creates an empty session — so `start_web.py` generates the greeting,
creates a session with it already appended (via the server's REST API, which *does* accept
seeded events), and prints you a URL to open. Run `adk web` first, then `start_web.py`.

The greeting is model-generated, so it's different every time.

---

## The six mechanisms

Every one of these appears exactly once, where it is the natural choice. Find them by
grepping for `MECHANISM` in the source.

| # | Mechanism | ADK feature | Lives in |
|---|---|---|---|
| 1 | LLM decides who handles it | `sub_agents=` → `transfer_to_agent` | `agent.py` |
| 2 | Tool writes to shared state | `tool_context.state[...]` | `tools.py` |
| 3 | Agent's reply writes to state | `output_key=` | `metrics.py`, `specialists.py` |
| 4 | Agent reads another's output | `{placeholder}` in `instruction` | `specialists.py`, `report.py` |
| 5 | Fixed order, no LLM involved | `SequentialAgent`, `ParallelAgent` | `agent.py`, `specialists.py` |
| 6 | Consult an agent, get a value back | `AgentTool(agent=...)` | `report.py` |

### The one that matters most: transfer vs. AgentTool

Both "call another agent." They are not interchangeable, and mixing them up is the most
common beginner mistake in ADK.

```python
sub_agents=[intake_agent]              # a HANDOFF
```
The model emits `transfer_to_agent("intake_agent")`. Control moves and **does not come
back** — `intake_agent` now owns the conversation and replies directly to the user. Use
this for routing: *"this request belongs to someone else."*

```python
tools=[AgentTool(agent=safety_reviewer)]   # a CALL
```
`safety_reviewer` runs, returns a string, and **the caller resumes** with that string.
Use this for consultation: *"I need an answer, then I'll carry on."*

`report_agent` needs the safety verdict *in order to write the document*, so a handoff
would be exactly wrong — it would never get to write anything.

### There are no messages

This is the thing that took me longest to see. Agents in ADK don't send each other
anything. `metrics_agent` writes its reply to `state["targets"]`; later, ADK substitutes
that value into `meal_designer`'s instruction where it says `{targets}`. That's it.
**Shared state is the message bus.** Watch the `state:` line in `run_cli.py` — keys appear
one at a time, and each new key is one agent handing off to the next.

---

## Three things that will bite you

**`{key}` vs `{key?}`** — a bare `{profile}` raises `KeyError` *before the model is ever
called* if that key isn't in state. The `?` suffix substitutes an empty string instead.
`coach` uses `{profile?}` because on turn one there is no profile; the specialists use a
bare `{targets}` deliberately, so that a pipeline running out of order fails loudly rather
than inventing a plan from nothing.

**Parallel branches share state but not history** — `ParallelAgent` gives each child its
own conversation branch, so `meal_designer` never sees `workout_designer`'s reasoning. But
they share one state object, which is why both can read `{targets}` and why both
`output_key` writes survive. Isolated history, shared state.

**`description` is written for the parent, not the user** — when `coach` decides where to
route, its model sees each child's `description` and nothing else. A vague description is
the usual reason routing misbehaves.

---

## Why the arithmetic is in a tool

`calculate_targets()` is plain Python. Models are unreliable at arithmetic and, worse,
*inconsistent* at it — ask one for a BMR three times and you can get three answers. So the
numbers are computed once, in code, and the agents' job is to gather inputs and explain
outputs. `metrics_agent`'s instruction says "do NOT do any arithmetic yourself."

This is also where the safety rules live, because they must be unskippable: a 500 kcal/day
deficit, floored at 1500 kcal (male) / 1200 (female), capped at 1 kg/week, with a refusal
if even maintenance sits below the floor. A prompt can be talked out of those. A function
cannot.

Run `test_tools.py` to see all of it asserted.

---

## Experiments

Things worth breaking, roughly in order of how much they teach:

1. **Turn the handoff into a call.** In `report.py`, move `safety_reviewer` from
   `tools=[AgentTool(...)]` to `sub_agents=[...]` and tell `report_agent` to transfer to
   it. The safety review happens, then the report is never written. That's mechanism 1 vs 6
   in one move.
2. **Break the data channel.** Delete `output_key=TARGETS_KEY` from `metrics_agent`. The
   pipeline dies with `KeyError: targets` when `meal_designer` builds its prompt — proving
   the `{targets}` placeholder, not any message, was carrying the data.
3. **Serialise the specialists.** Change `ParallelAgent` to `SequentialAgent` in
   `specialists.py` and time both. Same output, roughly double the wall clock.
4. **Starve the router.** Change `intake_agent`'s `description` to `"Does stuff."` and
   watch `coach` start routing badly.
5. **Break the auto-start.** Remove "in the SAME turn, immediately transfer to
   `plan_pipeline`" from `intake.py`'s instruction. Intake goes back to ending its turn
   after saving, and you have to type "build my plan" to continue — the friction that
   instruction exists to remove.
6. **Add a critic loop.** Wrap `report_agent` in a `LoopAgent` with a reviewer that calls
   the `exit_loop` tool when the plan is good enough. That's the fourth workflow agent, and
   the one this project doesn't use yet.

---

## Files

```
workout_agent/
  agent.py              wiring only — read this first, it's the map
  config.py             model name + the state keys, in one place
  tools.py              save_profile, calculate_targets (all the real math)
  sub_agents/
    intake.py           asks the 9 questions
    metrics.py          BMR/TDEE/targets            → state["targets"]
    specialists.py      workout + meal designers, in parallel
    report.py           fan-in + the safety reviewer AgentTool
run_cli.py              hand-wired Runner, shows what adk web hides
test_tools.py           8 tests over the deterministic half
```

Read them in the order `agent.py` → `config.py` → `tools.py` → the sub-agents.

---

## Notes

- **Model:** `gemini-flash-latest` (in `config.py`) — an alias that tracks the current
  flash model. This is not paranoia: `gemini-2.5-flash` is already refused for newly
  created API keys. Pin an explicit version only if you want reproducible output.
- **Cost:** a full conversation (greeting → intake → plan) is roughly a dozen model calls,
  because every tool call and every transfer costs a round trip on top of the six agents'
  own replies. Flash keeps that cheap; `gemini-pro-latest` writes noticeably better plans
  for noticeably more money.
- ADK prints a warning about `context_cache_config` on startup. It's telling you that every
  transfer swaps the system prompt and so re-sends the prompt uncached — the honest price of
  a multi-agent design, and harmless at this scale.
- The plans are real numbers from standard formulas (Mifflin–St Jeor), but this is general
  guidance, not medical advice.
