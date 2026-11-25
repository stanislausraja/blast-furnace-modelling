"""Consistency tests for the blast furnace model.  Run:  python -m pytest -q"""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "public"))

from bf_model import registry, run_json, schema_json  # noqa: E402
from bf_model.core.constants import M  # noqa: E402


def _ctx(**overrides):
    inp = registry.defaults()
    inp.update(overrides)
    ctx = {}
    for s in registry.SECTIONS:
        ctx[s.id] = s.compute(inp, ctx)
    return inp, ctx


def test_input_keys_unique():
    keys = [f.key for _, _, f in registry.all_fields()]
    assert len(keys) == len(set(keys))


def test_manifest_lists_every_python_file():
    pkg = ROOT / "public" / "bf_model"
    manifest = json.loads((pkg / "manifest.json").read_text())["files"]
    on_disk = {p.relative_to(pkg).as_posix() for p in pkg.rglob("*.py") if "__pycache__" not in p.parts}
    assert on_disk == set(manifest)


def test_default_run_has_no_errors_and_is_json():
    out = json.loads(run_json("{}"))
    assert out["errors"] == {}
    assert set(out["results"]) == {s.id for s in registry.SECTIONS}
    assert json.loads(schema_json())["sections"]


def test_total_mass_closes():
    _, ctx = _ctx()
    mb = ctx["mass_balance"]
    assert mb["m_in"] == pytest.approx(mb["m_out"], rel=1e-9)


def test_element_balances_close():
    _, ctx = _ctx(m_limestone=5.0)
    mb = ctx["mass_balance"]
    g = mb["gas"]
    # carbon: fuel C + limestone C = HM C + dust C + gas C
    C_in = mb["pool"]["C"] + mb["dust_comp"]["C"] + mb["n_caco3"] * M["C"]
    C_out = mb["hm_el"]["C"] + mb["dust_comp"]["C"] + (g["CO"] + g["CO2"]) * M["C"]
    assert C_in == pytest.approx(C_out, rel=1e-9)
    # nitrogen
    N_in = mb["n_N2_blast"] * M["N2"] + mb["pool"]["N"]
    assert N_in == pytest.approx(g["N2"] * M["N2"], rel=1e-9)
    # iron
    assert mb["fe_in"] == pytest.approx(mb["hm_el"]["Fe"] + mb["fe_slag"] + mb["fe_dust"], rel=1e-9)


def test_gas_profile_matches_top_and_bosh():
    _, ctx = _ctx()
    rows = ctx["composition"]["rows"]
    top_model = rows[-1][3]["gas"]
    g = ctx["mass_balance"]["gas"]
    for sp in ("CO", "CO2", "H2", "N2"):
        assert top_model[sp] == pytest.approx(g[sp], rel=0.02, abs=5)
    bosh = rows[0][3]["gas_pct"]
    assert bosh["CO2"] < 1.0           # no CO2 survives in the bosh gas


def test_thermal_profile_is_physical():
    inp, ctx = _ctx()
    t = ctx["temperature"]
    prof = t["profile"]
    assert prof[0][1] == pytest.approx(ctx["energy_balance"]["T_raft"])
    assert prof[-1][2] == pytest.approx(inp["t_charge"])
    assert all(tg >= ts - 1.0 for _, tg, ts in prof)          # gas is hotter than solids
    assert 40 < t["T_top_pred"] < 300


def test_more_coke_lowers_gas_utilisation():
    def eta(**kw):
        _, ctx = _ctx(**kw)
        g = ctx["mass_balance"]["gas"]
        return g["CO2"] / (g["CO"] + g["CO2"])
    assert eta(m_coke=100) < eta(m_coke=91)


def test_hotter_blast_raises_raft():
    _, a = _ctx(t_blast=1000)
    _, b = _ctx(t_blast=1250)
    assert b["energy_balance"]["T_raft"] > a["energy_balance"]["T_raft"]


@pytest.mark.parametrize("override", [
    {"m_pellet": 0, "m_lump": 0}, {"m_pci": 0}, {"v_o2": 0}, {"m_limestone": 20},
    {"humidity": 50}, {"m_sinter": 50},
])
def test_off_design_cases_do_not_crash(override):
    out = registry.run(override)
    assert out["errors"] == {}
