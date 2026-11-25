"""Section registry and model pipeline.

To add a new model:
  1. create bf_model/sections/<your_model>.py exposing SECTION = Section(...)
  2. import it below and append it to SECTIONS (order = calculation order;
     a section may read ctx[...] of any section listed before it)
  3. add the file path to bf_model/manifest.json (the browser loads files from there)
The web page creates the input form and the result tab automatically.
"""

import traceback

from .sections import geometry, mass_balance, energy_balance, temperature, composition

SECTIONS = [
    geometry.SECTION,
    mass_balance.SECTION,
    energy_balance.SECTION,
    temperature.SECTION,
    composition.SECTION,
]


def all_fields():
    for s in SECTIONS:
        for g in s.inputs:
            for f in g.fields:
                yield s, g, f


def defaults():
    return {f.key: f.default for _, _, f in all_fields()}


def schema():
    return {"sections": [s.meta() for s in SECTIONS]}


# KPIs shown on the overview page: (section id, KPI label)
HEADLINE = [
    ("mass_balance", "Hot metal production"), ("mass_balance", "Fuel rate"),
    ("mass_balance", "Coke rate (dry)"), ("mass_balance", "Gas utilisation ηCO"),
    ("mass_balance", "Slag"), ("energy_balance", "RAFT"), ("energy_balance", "Heat losses"),
    ("temperature", "Predicted top gas T"), ("temperature", "Thermal reserve zone T"),
    ("mass_balance", "Direct reduction degree r_d"),
]


def _headline(results):
    out = []
    for sid, label in HEADLINE:
        for k in results.get(sid, {}).get("kpis", []):
            if k["label"] == label:
                out.append(dict(k, section=sid))
    return out


def _overview(inp, ctx):
    """Data for the interactive furnace drawing."""
    geo = ctx["geometry"]["geo"]
    t = ctx.get("temperature")
    payload = {
        "profile": [[round(z, 3), round(r, 3)] for z, r in geo.profile()],
        "zones": [{"name": z["name"], "z0": z["z0"], "z1": z["z1"]} for z in geo.zones],
        "z_tuyere": geo.z_tuyere, "z_stockline": geo.z_stockline, "z_top": geo.z_top,
        "t_hm": inp["t_hm"], "center_index": inp["center_index"],
    }
    if t:
        prof = t["profile"]
        step = max(1, len(prof) // 80)
        payload["temp"] = [[round(z, 2), round(tg, 1), round(ts, 1)] for z, tg, ts in prof[::step]]
        payload["z_soft"], payload["z_melt"] = t["z_soft"], t["z_melt"]
        payload["t_raft"] = ctx["energy_balance"]["T_raft"]
    if "composition" in ctx:
        from .sections.composition import zone_info
        payload["zone_info"] = zone_info(inp, ctx)
    mb = ctx.get("mass_balance")
    if mb:
        payload["flows"] = {"hm": mb["hm"] / 1000, "slag": mb["m_slag"] / 1000,
                            "gas_nm3": sum(v for k, v in mb["gas"].items() if k != "H2O") * 22.414 / 1000,
                            "ore": mb["m_ore"] / 1000, "coke": mb["coke"]["wet"] / 1000,
                            "pci": mb["pci"]["wet"] / 1000, "blast": (mb["m_blast_gas"]) / 1000}
    return payload


def run(user_inputs=None):
    """Run every section in order. Returns a JSON-serialisable dict."""
    inp = defaults()
    for k, v in (user_inputs or {}).items():
        if k in inp and v is not None and v != "":
            inp[k] = float(v)
    ctx, results, errors = {}, {}, {}
    for s in SECTIONS:
        try:
            ctx[s.id] = s.compute(inp, ctx)
            results[s.id] = s.report(inp, ctx)
        except Exception as exc:  # keep other sections alive, show the error on the page
            errors[s.id] = f"{type(exc).__name__}: {exc}"
            results[s.id] = {"kpis": [], "tables": [], "charts": [], "warnings": [],
                             "error": errors[s.id], "trace": traceback.format_exc()}
    overview = None
    try:
        overview = _overview(inp, ctx)
        overview["headline"] = _headline(results)
        overview["warnings"] = [{"section": sid, "text": w} for sid, r in results.items() for w in r.get("warnings", [])]
    except Exception as exc:
        errors["overview"] = f"{type(exc).__name__}: {exc}"
    return {"inputs": inp, "results": results, "overview": overview, "errors": errors}
