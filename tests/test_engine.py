import inspect

import numpy as np
import pandas as pd
import pytest

from radar import engine
from radar.engine import assess, bh, cutoffs, windows

C, B = 8_500, 24_000
PARAMS = {"alpha": 0.05, "min_log2_ratio": 0.585}


def rows(*cases, C=C, B=B):
    """cases: (c, b) or (c, b, history_before)."""
    data = []
    for i, case in enumerate(cases):
        c, b, *hist = case
        data.append({"entity_id": f"E{i}", "c": c, "b": b, "C": C, "B": B,
                     "history_before": hist[0] if hist else 0})
    return pd.DataFrame(data)


def one(c, b, **kw):
    return assess(rows((c, b, *kw.pop("hist", ()))), **{**PARAMS, **kw}).iloc[0]


# 1. worked example and reference cases (04 §3) ------------------------------------------


def test_worked_example():
    r = one(25, 30)
    assert r.p == pytest.approx(0.0031, abs=5e-5)
    assert round(r.log2_sr, 3) == 1.239
    assert round(r.ci_low, 3) == 0.480
    assert round(r.ci_high, 3) == 1.998
    assert round(r["rank"], 3) == 0.480
    assert round(2 ** r.log2_sr, 2) == 2.36  # share ×2.36


@pytest.mark.parametrize("c,b,p,log2_sr,ci", [
    (6, 0, 0.00064, 5.198, None),
    (3, 0, 0.036, None, None),
    (2, 40, 0.00073, -2.520, (-4.363, -0.678)),
])
def test_reference_cases(c, b, p, log2_sr, ci):
    r = one(c, b)
    assert r.p == pytest.approx(p, rel=0.01)
    if log2_sr is not None:
        assert round(r.log2_sr, 3) == log2_sr
    if ci is not None:
        assert (round(r.ci_low, 3), round(r.ci_high, 3)) == ci


def test_three_works_do_not_survive_fdr_in_a_realistic_run():
    rng = np.random.default_rng(0)
    background = [(int(x), int(y)) for x, y in zip(rng.poisson(21.25, 300), rng.poisson(60, 300))]
    out = assess(rows((3, 0), *background), **PARAMS)
    assert not out.loc[out.entity_id == "E0", "is_signal"].iloc[0]


def test_bh_matches_definition():
    p = np.array([0.01, 0.04, 0.03, 0.2])
    assert np.allclose(bh(p), [0.04, 0.16 / 3, 0.16 / 3, 0.2])
    assert len(bh(np.array([]))) == 0


# 2–4. simulations -----------------------------------------------------------------------


def simulate(seed, n=2000, base_mean=60.0, planted=0, factor=3.0, varied=False):
    rng = np.random.default_rng(seed)
    lam_b = rng.uniform(10, 100, n) if varied else np.full(n, base_mean)
    lam_c = lam_b * C / B
    lam_c[:planted] *= factor
    df = pd.DataFrame({
        "entity_id": [f"E{i}" for i in range(n)],
        "c": rng.poisson(lam_c), "b": rng.poisson(lam_b),
        "C": C, "B": B, "history_before": 1, "planted": np.arange(n) < planted,
    })
    return df


def test_null_calibration():
    out = assess(simulate(seed=7, varied=True), **PARAMS)
    assert out["is_signal"].sum() <= 2


@pytest.mark.parametrize("seed", range(5))
def test_planted_effects(seed):
    out = assess(simulate(seed, planted=20), **PARAMS)
    recovered = (out.is_signal & out.planted).sum()
    false = (out.is_signal & ~out.planted).sum()
    assert recovered >= 18 and false <= 3


@pytest.mark.parametrize("seed", range(5))
def test_growth_invariance(seed):
    """Overall growth of the institution creates no signals (04 §1).

    Specs/04 §10 test 4 multiplies the observed current counts by 1.5. That also multiplies
    their random noise by 1.5 instead of sqrt(1.5), so a few null entities cross the threshold.
    The invariance is therefore checked two ways: real growth (Poisson counts at 1.5× the rate)
    keeps null entities null and planted ones found; deterministic scaling keeps every signal
    and leaves effect sizes unchanged.
    """
    df = simulate(seed, planted=20)
    rng = np.random.default_rng(100 + seed)
    lam_c = 60 * C / B * np.where(df.planted, 3.0, 1.0)
    grown = df.assign(c=rng.poisson(lam_c * 1.5), C=C * 1.5)
    out = assess(grown, **PARAMS)
    assert (out.is_signal & out.planted).sum() >= 18 and (out.is_signal & ~out.planted).sum() <= 3

    before = assess(df, **PARAMS).set_index("entity_id")
    scaled = assess(df.assign(c=np.round(df.c * 1.5).astype(int), C=C * 1.5), **PARAMS).set_index("entity_id")
    assert set(before.index[before.is_signal]) <= set(scaled.index[scaled.is_signal])
    planted_ids = df.entity_id[df.planted]
    diff = (before.loc[planted_ids, "log2_sr"] - scaled.loc[planted_ids, "log2_sr"]).abs()
    assert diff.max() < 0.05


# 5. labels ------------------------------------------------------------------------------


def test_labels():
    out = assess(rows((30, 0, 0), (30, 0, 4), (40, 30), (2, 60), (0, 60)), **PARAMS).set_index("entity_id")
    assert out.label.to_dict() == {"E0": "NEW", "E1": "RISING", "E2": "RISING", "E3": "FALLING", "E4": "GONE"}
    assert out.returning.to_dict() == {"E0": False, "E1": True, "E2": False, "E3": False, "E4": False}
    assert out.is_signal.all()


def test_non_signals_have_no_label_and_directions_filter():
    out = assess(rows((25, 72), (2, 60)), **PARAMS, directions={"up"}).set_index("entity_id")
    assert out.loc["E0", "label"] is None and not out.loc["E0", "is_signal"]  # unchanged share
    assert not out.loc["E1", "is_signal"]  # down not allowed


def test_effect_size_floor_blocks_large_trivial_changes():
    # a huge entity: share ×1.2 is highly significant but below the ×1.5 floor
    r = one(3060, 7200)
    assert r.q < 1e-6 and not r.is_signal


def test_rank_order_and_passthrough():
    df = rows((25, 30), (6, 0), (2, 40)).assign(extra=["a", "b", "c"])
    out = assess(df, **PARAMS)
    assert list(out["rank"]) == sorted(out["rank"], reverse=True)
    assert set(out.extra) == {"a", "b", "c"}
    assert out.loc[out.entity_id == "E2", "rank"].iloc[0] == pytest.approx(0.678, abs=1e-3)


def test_engine_has_no_detector_specific_code():
    source = inspect.getsource(engine).lower()
    for word in ("topic", "citation", "collaboration", "institution", "detector."):
        assert word not in source


# 8. windows -----------------------------------------------------------------------------


def test_year_mode_cutoffs():
    cs = cutoffs(2016, 2025, "year")
    assert [c.label for c in cs] == [str(y) for y in range(2019, 2026)]
    first = cs[0]
    assert first.current == range(36, 48) and first.baseline == range(0, 36)
    assert all(c.year_end for c in cs)


def test_semester_mode_cutoffs():
    cs = cutoffs(2016, 2025, "semester")
    assert len(cs) == 13
    assert cs[0].label == "2019-H2" and cs[1].label == "2020-H1" and cs[-1].label == "2025-H2"
    h1 = cs[1]
    assert h1.current == range(42, 54)  # Jul 2019 – Jun 2020
    assert not h1.year_end
    year_mode = {c.label: c for c in cutoffs(2016, 2025, "year")}
    for c in cs:
        if c.label.endswith("-H2"):
            ref = year_mode[c.label[:4]]
            assert (c.current, c.baseline, c.month) == (ref.current, ref.baseline, ref.month)


@pytest.mark.parametrize("mode", ["year", "semester"])
def test_baseline_is_36_months_just_before_current(mode):
    for c in cutoffs(2016, 2025, mode):
        assert len(c.current) == 12 and len(c.baseline) == 36
        assert c.baseline.stop == c.current.start and c.current.stop == c.month + 1
        assert windows(c.month) == (c.current, c.baseline)


def test_empty_denominator_does_not_poison_bh():
    df = pd.concat([rows((25, 30), (6, 0)), rows((7, 2), C=0, B=0).assign(entity_id="Z")], ignore_index=True)
    out = assess(df, **PARAMS).set_index("entity_id")
    assert out["q"].notna().all() and out["p"].notna().all()
    assert out.loc["Z", "p"] == 1.0 and not out.loc["Z", "is_signal"]
    assert out.loc["E0", "is_signal"] and out.loc["E1", "is_signal"]
