"""Plain Python functions that agents call as tools.

LEARNING NOTE — why is the arithmetic here and not in a prompt?

ADK builds each tool's JSON schema by reflecting over the function signature and
docstring, so the type hints and the docstring below are load-bearing: they are
literally what the model reads when deciding how to call these. But the more
important point is *what* lives in a tool. Language models are unreliable at
arithmetic and, worse, non-deterministic at it -- ask one to compute a BMR three
times and you can get three answers. Anything that must be correct and stable
belongs in Python. The model's job is to gather the inputs and explain the
outputs, not to be a calculator.
"""

from __future__ import annotations

from google.adk.tools import ToolContext

from .config import PROFILE_KEY

# --- Tunable constants (all standard, widely-used values) --------------------

# Mifflin-St Jeor is the BMR equation most dietetics bodies now recommend over
# the older Harris-Benedict.
_SEX_OFFSET = {"male": 5.0, "female": -161.0}

# How much a job alone moves total daily expenditure.
_JOB_FACTOR = {
    "sedentary": 1.20,   # desk work, driving, mostly seated
    "light": 1.30,       # teacher, retail, some standing and walking
    "moderate": 1.45,    # nurse, waiter, on your feet most of the day
    "heavy": 1.60,       # construction, farming, physical labour
}

# Extra on top of the job factor for deliberate training.
_TRAINING_BONUS = {
    "none": 0.00,
    "light": 0.05,       # 1-2 sessions/week
    "moderate": 0.10,    # 3-4 sessions/week
    "high": 0.15,        # 5+ sessions/week
}

# A 7700 kcal deficit is roughly 1 kg of fat.
_KCAL_PER_KG = 7700.0

# Target deficit: 500 kcal/day -> ~0.5 kg/week, the rate most guidelines call
# sustainable. We never exceed 1 kg/week.
_TARGET_DAILY_DEFICIT = 500.0
_MAX_WEEKLY_LOSS_KG = 1.0

# Never prescribe below these, regardless of what the arithmetic says.
_KCAL_FLOOR = {"male": 1500.0, "female": 1200.0}

_GOAL_LOSS_KG = 5.0
_PROTEIN_G_PER_KG = 1.6


def _norm(value: str, allowed: dict, default: str) -> str:
    """Map free-text the model produced onto one of our known buckets."""
    v = (value or "").strip().lower()
    return v if v in allowed else default


def save_profile(
    height_cm: float,
    weight_kg: float,
    age: int,
    sex: str,
    job: str,
    job_activity: str,
    training_level: str,
    dietary_preference: str,
    injuries: str,
    tool_context: ToolContext,
) -> dict:
    """Save the user's fitness profile. Call this once, after you have asked for
    and received every field. Do not guess or invent values.

    Args:
        height_cm: Height in centimetres, e.g. 175.
        weight_kg: Current bodyweight in kilograms, e.g. 85.
        age: Age in years.
        sex: Either "male" or "female" (needed for the BMR equation).
        job: The user's job in their own words, e.g. "software engineer".
        job_activity: How physical the job is. One of "sedentary" (desk work),
            "light" (some standing/walking), "moderate" (on their feet most of
            the day), "heavy" (physical labour).
        training_level: Current exercise habit. One of "none", "light" (1-2
            sessions a week), "moderate" (3-4), "high" (5 or more).
        dietary_preference: e.g. "no restrictions", "vegetarian", "vegan",
            "halal", "no dairy". Use "no restrictions" if the user has none.
        injuries: Any injuries, pain or medical conditions that affect exercise.
            Use "none" if the user reports nothing.

    Returns:
        A dict with the saved profile and a computed BMI.
    """
    sex_n = _norm(sex, _SEX_OFFSET, "male")
    bmi = round(weight_kg / ((height_cm / 100.0) ** 2), 1)

    profile = {
        "height_cm": float(height_cm),
        "weight_kg": float(weight_kg),
        "age": int(age),
        "sex": sex_n,
        "job": (job or "").strip(),
        "job_activity": _norm(job_activity, _JOB_FACTOR, "sedentary"),
        "training_level": _norm(training_level, _TRAINING_BONUS, "none"),
        "dietary_preference": (dietary_preference or "no restrictions").strip(),
        "injuries": (injuries or "none").strip(),
        "bmi": bmi,
    }

    # MECHANISM 2: a tool writing to session state. Everything a later agent
    # needs must go through here -- a tool's return value is only seen by the
    # agent that called it, but state is visible to the whole agent tree.
    tool_context.state[PROFILE_KEY] = profile

    return {"status": "saved", "profile": profile}


def calculate_targets(tool_context: ToolContext) -> dict:
    """Compute calorie and macro targets for losing 5 kg, from the saved profile.

    Reads the profile that save_profile stored, so it takes no arguments. Call
    this before designing any plan.

    Returns:
        A dict of BMR, TDEE, daily calorie target, protein target, the weekly
        loss rate and how many weeks 5 kg will take -- plus a `notes` list
        explaining any safety adjustment that was applied.
    """
    profile = tool_context.state.get(PROFILE_KEY)
    if not profile:
        return {
            "status": "error",
            "message": "No profile saved yet. Collect the profile first.",
        }

    sex = profile["sex"]
    weight = profile["weight_kg"]
    notes: list[str] = []

    # Mifflin-St Jeor.
    bmr = 10.0 * weight + 6.25 * profile["height_cm"] - 5.0 * profile["age"]
    bmr += _SEX_OFFSET[sex]

    multiplier = _JOB_FACTOR[profile["job_activity"]] + _TRAINING_BONUS[profile["training_level"]]
    tdee = bmr * multiplier

    # Start from the standard 500 kcal/day deficit, then apply the floor.
    target = tdee - _TARGET_DAILY_DEFICIT
    floor = _KCAL_FLOOR[sex]
    if target < floor:
        target = floor
        notes.append(
            f"A 500 kcal deficit would have put intake below the {floor:.0f} kcal "
            f"safety floor for this profile, so intake was raised to the floor and "
            f"the timeline extended instead."
        )

    actual_deficit = tdee - target
    weekly_loss = actual_deficit * 7.0 / _KCAL_PER_KG

    if weekly_loss > _MAX_WEEKLY_LOSS_KG:
        weekly_loss = _MAX_WEEKLY_LOSS_KG
        actual_deficit = weekly_loss * _KCAL_PER_KG / 7.0
        target = tdee - actual_deficit
        notes.append("Deficit capped at 1 kg/week, the upper end of a safe rate.")

    if weekly_loss <= 0:
        return {
            "status": "error",
            "message": "Maintenance calories are already at the safety floor; a "
                       "deficit cannot be prescribed safely. Recommend the user "
                       "speak to a doctor or dietitian.",
        }

    weeks = _GOAL_LOSS_KG / weekly_loss

    if profile["bmi"] < 18.5:
        notes.append(
            f"BMI is {profile['bmi']}, which is already underweight. Losing 5 kg "
            f"is not advisable -- flag this clearly and recommend professional advice."
        )
    elif profile["bmi"] < 20.0:
        notes.append(
            f"BMI is {profile['bmi']}, near the low end of normal. Losing 5 kg may "
            f"not be appropriate; mention this."
        )

    targets = {
        "status": "ok",
        "bmi": profile["bmi"],
        "bmr_kcal": round(bmr),
        "activity_multiplier": round(multiplier, 2),
        "tdee_kcal": round(tdee),
        "daily_calorie_target": round(target),
        "daily_deficit_kcal": round(actual_deficit),
        "protein_g_per_day": round(weight * _PROTEIN_G_PER_KG),
        "weekly_loss_kg": round(weekly_loss, 2),
        "weeks_to_goal": round(weeks, 1),
        "goal_loss_kg": _GOAL_LOSS_KG,
        "notes": notes,
    }

    # Stored under a separate key so `report_agent` can quote exact numbers
    # rather than trusting the prose the metrics agent wrote about them.
    tool_context.state["targets_raw"] = targets
    return targets
