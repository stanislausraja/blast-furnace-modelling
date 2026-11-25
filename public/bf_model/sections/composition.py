"""Solid, gas and product composition at every height of the furnace.

Reduction of the iron oxides follows the stepwise path
    Fe2O3 -> Fe3O4 -> FeO -> Fe
with each step's progress a smooth function of the local *solid* temperature
(from the thermal model). The last step is split into indirect (gas) and
direct (carbon / solution-loss) reduction using the degree of direct reduction
r_d obtained from the mass balance, so the profiles are consistent with the
top-gas analysis at the stockline and with the bosh gas at the tuyeres.

The gas composition at height z is the top gas minus everything the gas picks
up above z (oxygen removed from the burden, solution-loss carbon, calcination
CO2, moisture), i.e. an exact element balance over the volume above z.
"""

import math

from ..core.constants import M, NM3_PER_KMOL
from ..core.schema import Field, Group, Section, kpi, table, chart

INPUTS = [
    Group("kinetics", "Reduction Path Parameters", [
        Field("t_hem", "Fe₂O₃ → Fe₃O₄ (50 % conversion)", "°C", 520.0, 300, 800, 10),
        Field("t_mag", "Fe₃O₄ → FeO (50 % conversion)", "°C", 740.0, 500, 950, 10),
        Field("t_wus", "FeO → Fe indirect (50 % conversion)", "°C", 900.0, 700, 1100, 10),
        Field("red_width", "Transition width", "K", 45.0, 10, 150, 5,
              "Spread of each reduction step (larger = slower kinetics / wider zone)"),
    ], "Temperature windows of the stepwise reduction (semi-empirical).", True),
]


def _L(T, c, w):
    x = (T - c) / w
    if x > 60:
        return 1.0
    if x < -60:
        return 0.0
    return 1.0 / (1.0 + math.exp(-x))


def state_at(Ts, inp, mb):
    """Solid & gas state for a given local solid temperature."""
    w = inp["red_width"]
    nFe3, nFe2 = 2 * mb["n_fe2o3"], mb["n_feo"]
    h0 = nFe3 / (nFe3 + nFe2)
    w0 = 1 - h0
    y0 = 1.5 * h0 + w0
    r_d = min(max(mb["r_d"], 0.0), 1.0)
    p1, p2 = _L(Ts, inp["t_hem"], w), _L(Ts, inp["t_mag"], w)
    p3i, p3d = _L(Ts, inp["t_wus"], w), _L(Ts, inp["t_dr"], 50.0)
    p3 = (1 - r_d) * p3i + r_d * p3d
    hem = h0 * (1 - p1)
    m_formed = h0 * p1
    mag = m_formed * (1 - p2)
    wpool = w0 + m_formed * p2
    wus, fe = wpool * (1 - p3), wpool * p3
    y = 1.5 * hem + 4 / 3 * mag + wus
    y12 = 1.5 * hem + 4 / 3 * mag + wus + fe
    frac12 = (y0 - y12) / (y0 - 1) if y0 - 1 > 1e-9 else 1.0
    RD = 1 - y / y0

    # ------------------------------------------------ gas at this height
    nFe = mb["n_Fe_HM"]
    O12_total = mb["O_fe_removed"] - nFe
    O_ind_above = O12_total * frac12 + nFe * (1 - r_d) * wpool * p3i
    O_dir_above = nFe * r_d * wpool * p3d + mb["O_SiMnP"] * p3d
    phi_H = mb["n_H2O_red"] / mb["O_ind"] if mb["O_ind"] > 0 else 0.0
    pc, pe = _L(Ts, 850, 40), _L(Ts, 100, 10)
    g = mb["gas"]
    C = g["CO"] + g["CO2"] - O_dir_above - mb["n_caco3"] * pc
    O = g["CO"] + 2 * g["CO2"] - (1 - phi_H) * O_ind_above - O_dir_above - 2 * mb["n_caco3"] * pc
    gas = {
        "CO": max(2 * C - O, 0.0), "CO2": max(O - C, 0.0),
        "H2": g["H2"] + phi_H * O_ind_above,
        "H2O": max(g["H2O"] - phi_H * O_ind_above - mb["n_H2O_charge"] * pe, 0.0),
        "N2": g["N2"],
    }
    tot = sum(gas.values())
    eta = gas["CO2"] / (gas["CO"] + gas["CO2"]) if gas["CO"] + gas["CO2"] > 0 else 0
    melt = _L(Ts, 0.5 * (inp["t_soft"] + inp["t_melt"]), max((inp["t_melt"] - inp["t_soft"]) / 6, 5))
    dr_frac = O_dir_above / (mb["C_DR"]) if mb["C_DR"] > 0 else 0
    return {
        "fe_phase": {"Fe₂O₃": hem * 100, "Fe₃O₄": mag * 100, "FeO": wus * 100, "Fe (metallic)": fe * 100},
        "RD": RD * 100, "gas_pct": {k: v / tot * 100 for k, v in gas.items()}, "gas": gas, "eta_co": eta * 100,
        "melt": melt * 100, "dr_frac": min(max(dr_frac, 0.0), 1.0), "calc": pc * 100,
    }


def compute(inp, ctx):
    mb = ctx["mass_balance"]
    t = ctx["temperature"]
    prof = t["profile"]
    rows = [(z, Tg, Ts, state_at(Ts, inp, mb)) for z, Tg, Ts in prof]
    return {"rows": rows}


def _zone_rows(inp, ctx):
    from .temperature import _interp, _state
    geo = ctx["geometry"]["geo"]
    mb, en = ctx["mass_balance"], ctx["energy_balance"]
    prof = ctx["temperature"]["profile"]
    zones = []
    for zn in geo.zones:
        if zn["name"] == "Hearth":
            continue
        z_lo = max(zn["z0"], geo.z_tuyere)
        z_hi = min(zn["z1"], geo.z_stockline)
        zm = 0.5 * (z_lo + z_hi)
        Ts, Tg = _interp(prof, zm, 2), _interp(prof, zm, 1)
        zones.append((zn["name"], zn["z0"], zn["z1"], zm, Tg, Ts, state_at(Ts, inp, mb), _state(Ts, inp)))
    return zones


def zone_info(inp, ctx):
    """Per-zone summary for the interactive furnace drawing."""
    mb, en = ctx["mass_balance"], ctx["energy_balance"]
    geo = ctx["geometry"]["geo"]
    hm = mb["hm"]
    out = []
    for name, z0, z1, zm, Tg, Ts, s, state in reversed(_zone_rows(inp, ctx)):
        gp = s["gas_pct"]
        fp = s["fe_phase"]
        out.append({"name": name, "z0": z0, "z1": z1, "state": state, "items": [
            ["Gas temperature", round(Tg), "°C"], ["Solid temperature", round(Ts), "°C"],
            ["Reduction degree", round(s["RD"], 1), "%"], ["Gas utilisation ηCO", round(s["eta_co"], 1), "%"],
            ["Gas CO / CO₂", f"{gp['CO']:.1f} / {gp['CO2']:.1f}", "vol %"],
            ["Gas H₂ / N₂", f"{gp['H2']:.1f} / {gp['N2']:.1f}", "vol %"],
            ["Iron as Fe₂O₃ / Fe₃O₄", f"{fp['Fe₂O₃']:.0f} / {fp['Fe₃O₄']:.0f}", "%"],
            ["Iron as FeO / Fe", f"{fp['FeO']:.0f} / {fp['Fe (metallic)']:.0f}", "%"],
            ["Molten fraction", round(s["melt"], 0), "%"],
        ]})
    rg = en["raceway_gas"]
    n = sum(rg.values())
    out.append({"name": "Raceway", "z0": geo.z_tuyere - 0.4, "z1": geo.z_tuyere + 0.4,
                "state": "Coke & coal combustion in front of the tuyeres", "items": [
                    ["Flame temperature (RAFT)", round(en["T_raft"]), "°C"],
                    ["Bosh gas CO", round(rg["CO"] / n * 100, 1), "vol %"],
                    ["Bosh gas H₂", round(rg["H2"] / n * 100, 1), "vol %"],
                    ["Bosh gas N₂", round(rg["N2"] / n * 100, 1), "vol %"],
                    ["Bosh gas volume", round(n * NM3_PER_KMOL / hm * 1000), "Nm³/tHM"],
                    ["Blast temperature", round(inp["t_blast"]), "°C"],
                ]})
    sl = mb["slag"]
    ms = mb["m_slag"]
    out.append({"name": "Hearth", "z0": 0, "z1": geo.z_tuyere,
                "state": "Liquid hot metal under slag, coke deadman", "items": [
                    ["Hot metal", round(hm / 1000, 1), "t/h"], ["Slag", round(ms / 1000, 1), "t/h"],
                    ["Hot metal T", round(inp["t_hm"]), "°C"],
                    ["HM C / Si", f"{inp['hm_c']:.2f} / {inp['hm_si']:.2f}", "wt %"],
                    ["Slag CaO / SiO₂", f"{sl['CaO'] / ms * 100:.1f} / {sl['SiO2'] / ms * 100:.1f}", "wt %"],
                    ["Slag Al₂O₃ / MgO", f"{sl['Al2O3'] / ms * 100:.1f} / {sl['MgO'] / ms * 100:.1f}", "wt %"],
                    ["Basicity B2", round(sl["CaO"] / sl["SiO2"], 2) if sl["SiO2"] > 0 else "-", ""],
                ]})
    return out


def report(inp, ctx):
    c = ctx["composition"]
    mb = ctx["mass_balance"]
    rows = c["rows"]
    zs = [round(r[0], 3) for r in rows]
    phase_colors = {"Fe₂O₃": "#b03a2e", "Fe₃O₄": "#4a4a4a", "FeO": "#8e6c4a", "Fe (metallic)": "#9fb8c8"}
    phase = chart("fe_phase", "Iron-bearing burden: phase distribution of Fe (%)", [
        {"type": "scatter", "x": [round(r[3]["fe_phase"][k], 2) for r in rows], "y": zs, "name": k,
         "stackgroup": "fe", "orientation": "h", "mode": "lines", "line": {"width": 0.5, "color": col},
         "fillcolor": col} for k, col in phase_colors.items()
    ], {"height": 520, "xaxis": {"title": "% of iron", "range": [0, 100]}, "yaxis": {"title": "Height (m)"}})
    gas_colors = {"CO": "#f08a24", "CO2": "#8c8c8c", "H2": "#5fa8d3", "H2O": "#9ad0ec", "N2": "#3f6e9a"}
    gas = chart("gas_profile", "Gas composition along the height (vol %, wet)", [
        {"type": "scatter", "x": [round(r[3]["gas_pct"][k], 2) for r in rows], "y": zs, "name": k, "mode": "lines",
         "line": {"width": 3, "color": col}} for k, col in gas_colors.items()
    ], {"height": 520, "xaxis": {"title": "vol %"}, "yaxis": {"title": "Height (m)"}})
    progress = chart("progress", "Reduction degree, gas utilisation and melting", [
        {"type": "scatter", "x": [round(r[3]["RD"], 2) for r in rows], "y": zs, "name": "Reduction degree (%)",
         "mode": "lines", "line": {"width": 3, "color": "#9fb8c8"}},
        {"type": "scatter", "x": [round(r[3]["eta_co"], 2) for r in rows], "y": zs, "name": "ηCO (%)",
         "mode": "lines", "line": {"width": 3, "color": "#f08a24"}},
        {"type": "scatter", "x": [round(r[3]["melt"], 2) for r in rows], "y": zs, "name": "Molten fraction (%)",
         "mode": "lines", "line": {"width": 3, "dash": "dot", "color": "#ff5a1f"}},
    ], {"height": 520, "xaxis": {"title": "%", "range": [0, 102]}, "yaxis": {"title": "Height (m)"}})

    # ------------------------------------------------------ Rist diagram
    nFe = mb["n_Fe_HM"]
    R = (mb["C_tuyere"] + mb["C_DR"] + mb["H2_total"]) / nFe
    yb = mb["C_tuyere"] / nFe
    x_top = (mb["C_tuyere"] + mb["O_removed"]) / (nFe * R)
    y_top = R * x_top - yb
    rist = chart("rist", "Rist operating diagram (C + H₂ as reductants)", [
        {"type": "scatter", "x": [0, x_top], "y": [-yb, y_top], "mode": "lines+markers", "name": "Operating line",
         "line": {"color": "#f08a24", "width": 3}},
        {"type": "scatter", "x": [1.0], "y": [R * 1 - yb], "mode": "markers+text", "text": ["  P (x = 1)"],
         "textposition": "middle right", "name": "Direct/indirect boundary", "marker": {"size": 10, "color": "#5fa8d3"}},
        {"type": "scatter", "x": [1.29], "y": [1.05], "mode": "markers+text", "text": ["  W (wüstite eq.)"],
         "textposition": "middle right", "name": "Wüstite point", "marker": {"size": 10, "symbol": "x", "color": "#7CFC9A"}},
    ], {"height": 440, "xaxis": {"title": "x = O / (C + H₂) of gas", "range": [0, 2]},
        "yaxis": {"title": "y = O / Fe"}, "shapes": [
            {"type": "line", "x0": 0, "x1": 2, "y0": 0, "y1": 0, "line": {"color": "#777", "width": 1}},
            {"type": "line", "x0": 1, "x1": 1, "y0": -yb - 0.3, "y1": y_top + 0.2, "line": {"color": "#777", "dash": "dot"}}]},
        note=f"Slope μ = (C + H₂)/Fe = {R:.2f} mol/mol Fe. Top gas at x = {x_top:.3f}.")

    zone_rows = []
    for name, z0, z1, zm, Tg, Ts, s, state in _zone_rows(inp, ctx):
        fp, gp = s["fe_phase"], s["gas_pct"]
        zone_rows.append([name, Ts, s["RD"], fp["Fe₂O₃"], fp["Fe₃O₄"], fp["FeO"], fp["Fe (metallic)"],
                          gp["CO"], gp["CO2"], gp["H2"], gp["N2"], s["eta_co"], state])
    top = rows[-1][3]["gas_pct"]
    bosh = rows[0][3]["gas_pct"]
    hm = mb["hm"]
    ms = mb["m_slag"]
    product_rows = [["Hot metal", ", ".join(f"{el} {mb['hm_el'][el] / hm * 100:.2f}" for el in ("Fe", "C", "Si", "Mn", "P", "S"))],
                    ["Slag", ", ".join(f"{k} {v / ms * 100:.1f}" for k, v in mb["slag"].items())],
                    ["Top gas (wet)", ", ".join(f"{k} {v:.1f}" for k, v in top.items())],
                    ["Bosh gas", ", ".join(f"{k} {v:.1f}" for k, v in bosh.items() if v > 0.05)],
                    ["Dust", ", ".join(f"{k} {v / mb['dust'] * 100:.0f}" for k, v in mb["dust_comp"].items())]]
    charge_rows = []
    for name, wet, dry, fe, comp in mb["charge_detail"]:
        if wet <= 0:
            continue
        charge_rows.append([name] + [comp[k] / dry * 100 for k in ("Fe2O3", "FeO", "SiO2", "Al2O3", "CaO", "MgO", "other")]
                           + [(wet - dry) / wet * 100])
    return {
        "kpis": [
            kpi("Top gas CO / CO₂", f"{top['CO']:.1f} / {top['CO2']:.1f}", "vol %"),
            kpi("Top gas H₂ / N₂", f"{top['H2']:.1f} / {top['N2']:.1f}", "vol %"),
            kpi("Bosh gas CO", bosh["CO"], "vol %", 1),
            kpi("Indirect reduction", (1 - mb["r_d"]) * 100, "% of FeO→Fe", 1),
            kpi("H₂ share of indirect reduction", mb["n_H2O_red"] / mb["O_ind"] * 100 if mb["O_ind"] > 0 else 0, "%", 1),
            kpi("Rist slope μ", R, "mol/mol Fe", 2),
        ],
        "charts": [phase, gas, progress, rist],
        "tables": [
            table("Composition at each zone (mid-height)",
                  ["Zone", "Ts (°C)", "Red. degree (%)", "Fe₂O₃", "Fe₃O₄", "FeO", "Fe", "CO", "CO₂", "H₂", "N₂",
                   "ηCO (%)", "State"], zone_rows, 1,
                  "Iron phases in % of Fe; gas in vol % (wet)."),
            table("Products", ["Stream", "Composition (wt % / vol %)"], product_rows),
            table("Raw-material chemistry (dry basis, wt %)",
                  ["Material", "Fe₂O₃", "FeO", "SiO₂", "Al₂O₃", "CaO", "MgO", "Other", "Moisture"], charge_rows),
        ],
        "warnings": [],
    }


SECTION = Section("composition", "Chemical Composition",
                  "Iron-oxide phases, gas composition and products at every position in the furnace.",
                  compute, report, INPUTS, icon="flask")
