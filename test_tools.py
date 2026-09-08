"""Tests for the deterministic half of the system.

These are the parts worth asserting on: the tools are pure functions of the
profile, so the numbers are the same every run. The agents' prose is not
testable this way, which is exactly why the arithmetic was pushed out of the
prompts and into tools.py.

Run:  .venv/bin/python test_tools.py
"""

from workout_agent.tools import calculate_targets, save_profile


class FakeToolContext:
    """Stand-in for ADK's ToolContext -- the tools only ever touch `.state`."""

    def __init__(self):
        self.state = {}


def _profile(**over):
    args = dict(
        height_cm=175, weight_kg=85, age=30, sex="male",
        job="software engineer", job_activity="sedentary",
        training_level="none", dietary_preference="no restrictions",
        injuries="none",
    )
    args.update(over)
    ctx = FakeToolContext()
    save_profile(tool_context=ctx, **args)
    return ctx


def test_baseline():
    """175 cm, 85 kg, 30 y, male, desk job, no training."""
    t = calculate_targets(_profile())
    # Mifflin-St Jeor: 10*85 + 6.25*175 - 5*30 + 5 = 1798.75
    assert t["bmr_kcal"] == 1799, t["bmr_kcal"]
    # 1798.75 * 1.20 (sedentary job, no training) = 2158.5
    assert t["tdee_kcal"] == 2158, t["tdee_kcal"]
    assert t["daily_calorie_target"] == 1658, t["daily_calorie_target"]
    assert t["daily_deficit_kcal"] == 500, t["daily_deficit_kcal"]
    # 500 kcal/day * 7 / 7700 = 0.4545 kg/wk -> 5 kg in 11 weeks
    assert t["weekly_loss_kg"] == 0.45, t["weekly_loss_kg"]
    assert t["weeks_to_goal"] == 11.0, t["weeks_to_goal"]
    assert t["protein_g_per_day"] == 136, t["protein_g_per_day"]
    assert t["bmi"] == 27.8, t["bmi"]
    assert t["notes"] == []
    print("baseline                     ok")


def test_job_and_training_raise_tdee():
    """A physical job and regular training must raise maintenance calories."""
    desk = calculate_targets(_profile())
    labour = calculate_targets(_profile(job_activity="heavy", training_level="high"))
    assert labour["tdee_kcal"] > desk["tdee_kcal"]
    # 1.60 + 0.15 = 1.75 vs 1.20
    assert labour["activity_multiplier"] == 1.75, labour["activity_multiplier"]
    # Higher burn -> same deficit reached with more food, and faster loss.
    assert labour["daily_calorie_target"] > desk["daily_calorie_target"]
    print("job/training raise tdee      ok")


def test_calorie_floor_binds():
    """A smaller sedentary woman: a full 500 kcal deficit would go below 1200.

    The floor must win, and the timeline must stretch to absorb it -- the plan
    is allowed to take longer, it is not allowed to under-feed someone.
    """
    t = calculate_targets(_profile(height_cm=160, weight_kg=60, age=40, sex="female"))
    assert t["status"] == "ok", t
    assert t["daily_calorie_target"] == 1200, t["daily_calorie_target"]
    assert t["daily_deficit_kcal"] < 500, t["daily_deficit_kcal"]
    # Smaller deficit must mean a longer timeline, not a broken promise.
    assert t["weeks_to_goal"] > 11.0, t["weeks_to_goal"]
    assert any("floor" in n for n in t["notes"]), t["notes"]
    print("calorie floor binds          ok")


def test_refuses_when_maintenance_is_below_the_floor():
    """If even maintenance sits under the floor, no deficit is safe at all.

    150 cm / 50 kg / 65 y female has a TDEE around 1142, below the 1200 floor.
    The correct answer is to refuse and point at a professional, not to invent
    a deficit.
    """
    t = calculate_targets(_profile(height_cm=150, weight_kg=50, age=65, sex="female"))
    assert t["status"] == "error", t
    assert "doctor" in t["message"] or "dietitian" in t["message"], t["message"]
    print("refuses unsafe deficit       ok")


def test_weekly_loss_never_unsafe():
    """Even a very large person must not be given more than 1 kg/week."""
    t = calculate_targets(_profile(weight_kg=200, height_cm=190, age=25))
    assert t["weekly_loss_kg"] <= 1.0, t["weekly_loss_kg"]
    print("weekly loss capped           ok")


def test_low_bmi_is_flagged():
    """Someone already underweight must be warned, not quietly given a deficit."""
    t = calculate_targets(_profile(height_cm=180, weight_kg=55, sex="female"))
    assert t["bmi"] < 18.5, t["bmi"]
    assert any("underweight" in n for n in t["notes"]), t["notes"]
    print("low bmi flagged              ok")


def test_missing_profile_is_an_error_not_a_crash():
    out = calculate_targets(FakeToolContext())
    assert out["status"] == "error", out
    print("missing profile handled      ok")


def test_freetext_buckets_are_normalised():
    """The model may pass something outside our vocabulary; don't KeyError."""
    ctx = _profile(job_activity="desk-bound", training_level="occasionally", sex="M")
    p = ctx.state["profile"]
    assert p["job_activity"] == "sedentary", p["job_activity"]
    assert p["training_level"] == "none", p["training_level"]
    assert p["sex"] == "male", p["sex"]
    assert calculate_targets(ctx)["status"] == "ok"
    print("free-text normalised         ok")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
    print("\nall tests passed")
