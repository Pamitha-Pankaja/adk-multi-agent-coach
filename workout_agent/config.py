"""Shared configuration for every agent in this project."""

# One constant so you can swap the model everywhere from a single place.
# A flash model matters here because a single user turn can fan out into five
# separate model calls (coach -> metrics -> two specialists -> report).
#
# "gemini-flash-latest" is an alias that always points at the current flash
# model, so this project will not break when a specific version is retired --
# which is not hypothetical: "gemini-2.5-flash" is already refused for new API
# keys. Pin an explicit version (e.g. "gemini-3.8-flash") only if you want
# reproducible output. Swap in "gemini-pro-latest" to compare plan quality.
MODEL = "gemini-flash-latest"

# Session-state keys. These strings are the wiring between agents: one agent
# writes a key (via output_key or a tool), a later agent reads it (via a
# {placeholder} in its instruction). Keeping them here makes the data flow
# greppable instead of scattered through prompt text.
PROFILE_KEY = "profile"          # written by  save_profile tool
TARGETS_KEY = "targets"          # written by  metrics_agent   (output_key)
WORKOUT_KEY = "workout_plan"     # written by  workout_designer(output_key)
MEAL_KEY = "meal_plan"           # written by  meal_designer   (output_key)
REPORT_KEY = "final_plan"        # written by  report_agent    (output_key)
