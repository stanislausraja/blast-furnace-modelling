"""Axial gas/solid temperature distribution (1-D counter-current heat exchanger).

    gas (upwards):    W_g dTg/dz = -h_v A(z) (Tg - Ts) - q_wall(z)
    solids (down):    W_s,eff(Ts) dTs/dz = -h_v A(z) (Tg - Ts)

W_s,eff is an *apparent* heat-capacity flow: the sensible heat capacity of the
burden plus the reaction / phase-change heats taken from the mass & energy
balances (moisture evaporation, calcination, direct reduction + solution loss,
melting), each released over a temperature window. This reproduces the
thermal reserve zone without empirical temperature profiles.

Boundary conditions: Tg = RAFT at the tuyeres, Ts = charge temperature at the
stockline; solved by shooting on Ts at the tuyeres. Radial (2-D) field is
obtained by shifting isotherms according to the gas-distribution index.
"""

import math

from ..core.schema import Field, Group, Section, kpi, table, chart
from ..core.thermo import cp_mix, cp_solid_burden

INPUTS = [
    Group("thermal_model", "Thermal Model Parameters", [
        Field("t_charge", "Burden charging temperature", "°C", 25.0, 0, 100, 1),
        Field("h_v", "Heat transfer coeff. – granular shaft", "kW/m³·K", 2.0, 0.3, 10, 0.1,
              "Volumetric gas-solid coefficient in the lumpy zone"),
        Field("h_v_low", "Heat transfer coeff. – dripping zone", "kW/m³·K", 0.25, 0.05, 5, 0.05,
              "Below the softening isotherm (coke bed, dripping liquids)"),
        Field("t_dr", "Solution-loss / direct reduction onset", "°C", 1050.0, 900, 1200, 10,
              "Centre of the temperature window where C + CO₂ → 2CO becomes active"),
        Field("t_soft", "Softening temperature (cohesive zone top)", "°C", 1200.0, 1000, 1350, 10),
        Field("t_melt", "Melting temperature (cohesive zone bottom)", "°C", 1380.0, 1250, 1550, 10),
        Field("center_index", "Central gas-flow index", "m", 3.0, -3, 8, 0.1,
              "Vertical rise of isotherms at the axis vs. the wall (positive = centre-working, inverted-V)"),
    ], "Parameters of the 1-D/2-D thermal model.", True),
]

# same colour map as the furnace drawing (assets/js/furnace.js), 0-2100 degC
FURNACE_COLORSCALE = [[t / 2100, c] for t, c in [
    (0, "rgb(11,11,38)"), (150, "rgb(42,11,87)"), (350, "rgb(92,18,110)"), (550, "rgb(138,34,106)"),
    (750, "rgb(183,55,89)"), (950, "rgb(221,81,56)"), (1150, "rgb(243,120,25)"), (1350, "rgb(252,165,10)"),
    (1650, "rgb(246,215,70)"), (2100, "rgb(252,255,164)")]]

LATENT_MELT_HM = 270.0   # kJ/kg (fusion of hot metal incl. carburisation effects)
LATENT_MELT_SLAG = 500.0  # kJ/kg


def _window(T, centre, width):
    """Normalised Gaussian (1/K)."""
    return math.exp(-0.5 * ((T - centre) / width) ** 2) / (width * math.sqrt(2 * math.pi))


def _build(inp, ctx):
    geo = ctx["geometry"]["geo"]
    mb, en = ctx["mass_balance"], ctx["energy_balance"]
    # descending solids lose oxygen, coke (solution loss) and volatiles: the heat-capacity flow
    # shrinks from the full burden at the top to hot metal + slag + raceway coke at the tuyeres
    m_top = (mb["m_ore"] + mb["coke"]["wet"] + mb["lime"]) / 3600.0                     # kg/s
    C_coke_raceway = max(mb["C_tuyere"] - mb["pci"]["C"] / 12.011, 0.0) * 12.011
    m_bot = (mb["hm"] + mb["m_slag"] + C_coke_raceway) / 3600.0
    gas_top = {k: v / 3600.0 for k, v in mb["gas"].items()}                 # kmol/s
    gas_top["H2O"] -= mb["n_H2O_charge"] / 3600.0                           # moisture joins only near the top
    gas_bosh = {k: v / 3600.0 for k, v in ctx["energy_balance"]["raceway_gas"].items()}
    sinks = [  # (kW total, centre degC, width K)
        (en["Q_evap"] / 3600.0, 100.0, 15.0),
        (en["Q_calc"] / 3600.0, 850.0, 50.0),
        (en["Q_dr"] / 3600.0, inp["t_dr"], 70.0),
        ((mb["hm"] * LATENT_MELT_HM + mb["m_slag"] * LATENT_MELT_SLAG) / 3600.0,
         0.5 * (inp["t_soft"] + inp["t_melt"]), max((inp["t_melt"] - inp["t_soft"]) / 4, 20.0)),
    ]
    z0, z1 = geo.z_tuyere, geo.z_stockline
    # wall heat loss above the tuyeres, distributed by wall area (~ diameter)
    q_loss = max(en["Q_loss"], 0.0) / 3600.0 * 0.6          # ~60 % of losses above tuyeres (rest hearth/tuyeres)
    perim_int = sum(geo.radius(z0 + (i + 0.5) * (z1 - z0) / 200) for i in range(200)) * (z1 - z0) / 200

    def _sig(T, c, w):
        return 1.0 / (1.0 + math.exp(-max(min((T - c) / w, 60), -60)))

    def W_g(Tg):
        f = _sig(Tg, inp["t_dr"] + 150, 80)                   # 1 = bosh gas, 0 = shaft gas
        return f * cp_mix(gas_bosh, Tg) + (1 - f) * cp_mix(gas_top, Tg)   # kmol/s * J/mol/K = kW/K

    def W_s(Ts):
        m_s = m_bot + (m_top - m_bot) * (1 - _sig(Ts, 950, 120))
        w = m_s * cp_solid_burden(Ts)
        for Q, c, wd in sinks:
            w += Q * _window(Ts, c, wd)
        return w

    # lookup tables (1 K resolution) make the iterative solver ~10x faster - important in the browser
    T_MAX = 2600
    Wg_tab = [W_g(float(T)) for T in range(T_MAX + 1)]
    Ws_tab = [W_s(float(T)) for T in range(T_MAX + 1)]
    # heat-transfer coefficient: shaft value in the granular zone, lower value in the coke/dripping zone
    hv_tab = [inp["h_v"] + (inp["h_v_low"] - inp["h_v"]) * _sig(float(T), inp["t_soft"], 25) for T in range(T_MAX + 1)]

    def _ix(T):
        return 0 if T < 0 else (T_MAX if T > T_MAX else int(T))

    def solve(n=240, tol=0.05, max_iter=800):
        """Alternate an upward gas march and a downward solids march until both profiles converge.

        Each step uses the exact exponential solution of dT/dz = -(hA/W)(T - T_other), which is
        unconditionally stable even when the heat-transfer length is much shorter than the cell.
        """
        exp = math.exp
        dz = (z1 - z0) / n
        zs = [z0 + i * dz for i in range(n + 1)]
        zm = [z + dz / 2 for z in zs[:-1]]
        A = [geo.area(z) * dz for z in zm]
        qw = [q_loss * geo.radius(z) / perim_int * dz for z in zm]
        T_raft, T_ch = en["T_raft"], inp["t_charge"]
        Tg = [T_raft - (T_raft - 200) * i / n for i in range(n + 1)]
        Ts = [1450 - (1450 - T_ch) * i / n for i in range(n + 1)]
        it = 0
        for it in range(max_iter):
            change = 0.0
            Tg[0] = T_raft
            hA = [hv_tab[_ix(0.5 * (Ts[i] + Ts[i + 1]))] * A[i] for i in range(n)]
            for i in range(n):
                Tsm = 0.5 * (Ts[i] + Ts[i + 1])
                wg = Wg_tab[_ix(Tg[i])]
                new = Tsm + (Tg[i] - Tsm) * exp(-hA[i] / wg) - qw[i] / wg
                d = abs(new - Tg[i + 1])
                if d > change:
                    change = d
                Tg[i + 1] = new
            Ts[n] = T_ch
            for i in range(n - 1, -1, -1):
                Tgm = 0.5 * (Tg[i] + Tg[i + 1])
                new = Tgm + (Ts[i + 1] - Tgm) * exp(-hA[i] / Ws_tab[_ix(Ts[i + 1])])
                d = abs(new - Ts[i])
                if d > change:
                    change = d
                Ts[i] = new
            if change < tol:
                break
        return list(zip(zs, Tg, Ts)), it + 1

    return solve, W_g, W_s, sinks


def compute(inp, ctx):
    solve, W_g, W_s, sinks = _build(inp, ctx)
    prof, iterations = solve()
    geo = ctx["geometry"]["geo"]
    z_t = geo.z_tuyere
    profile = prof[::2]
    if profile[-1] != prof[-1]:
        profile.append(prof[-1])

    # thermal reserve zone: region where Tg - Ts < 50 K and 800 < Ts < 1100
    trz = [p for p in profile if p[1] - p[2] < 50 and 750 < p[2] < 1100]
    trz_range = (min(p[0] for p in trz), max(p[0] for p in trz)) if trz else None
    trz_T = sum(p[2] for p in trz) / len(trz) if trz else None

    def z_at(T):
        """Height where Ts crosses T (on the axis-equivalent 1-D profile)."""
        for (za, _, ta), (zb, _, tb) in zip(profile, profile[1:]):
            if (ta - T) * (tb - T) <= 0 and ta != tb:
                return za + (T - ta) * (zb - za) / (tb - ta)
        return None

    return {"profile": profile, "T_top_pred": prof[-1][1], "Ts_tuyere": prof[0][2],
            "trz_range": trz_range, "trz_T": trz_T,
            "z_soft": z_at(inp["t_soft"]), "z_melt": z_at(inp["t_melt"]), "z_tuyere": z_t,
            "W_ratio_top": W_s(200) / W_g(250), "iterations": iterations}


def _interp(profile, z, col):
    if z <= profile[0][0]:
        return profile[0][col]
    for a, b in zip(profile, profile[1:]):
        if a[0] <= z <= b[0]:
            f = (z - a[0]) / (b[0] - a[0])
            return a[col] + f * (b[col] - a[col])
    return profile[-1][col]


def temperature_field(inp, ctx, nr=41, nz=90):
    """2-D (r, z) solid temperature field for the vertical section, NaN outside the furnace."""
    geo = ctx["geometry"]["geo"]
    t = ctx["temperature"]
    prof = t["profile"]
    T_hm = inp["t_hm"]
    R = max(geo.rb, geo.rh, geo.rt)
    xs = [-R + 2 * R * i / (nr - 1) for i in range(nr)]
    zs = [geo.z_top * j / (nz - 1) for j in range(nz)]
    s = inp["center_index"]
    field = []
    for z in zs:
        row = []
        rz = geo.radius(z)
        for x in xs:
            if abs(x) > rz + 1e-9 or z > geo.z_stockline + 0.3:
                row.append(None)
                continue
            if z <= geo.z_tuyere:
                row.append(round(T_hm, 1))
                continue
            xi = abs(x) / rz
            shift = s * (1 - xi ** 2) - 0.25 * s     # centre hotter, wall slightly cooler
            ze = z - shift * min(1.0, (z - geo.z_tuyere) / 3.0)
            row.append(round(_interp(prof, max(ze, geo.z_tuyere), 2), 1))
        field.append(row)
    return xs, zs, field


def report(inp, ctx):
    t = ctx["temperature"]
    geo = ctx["geometry"]["geo"]
    prof = t["profile"]
    zs = [round(p[0], 3) for p in prof]
    zone_shapes = [{"type": "rect", "xref": "paper", "x0": 0, "x1": 1, "y0": zn["z0"], "y1": zn["z1"],
                    "fillcolor": c, "opacity": 0.06, "line": {"width": 0}}
                   for zn, c in zip(geo.zones, ["#fff", "#000"] * 3)]
    annotations = [{"xref": "paper", "x": 1.0, "y": (zn["z0"] + zn["z1"]) / 2, "text": zn["name"],
                    "showarrow": False, "xanchor": "right", "font": {"size": 11, "color": "#999"}}
                   for zn in geo.zones]
    if t["trz_range"]:
        zone_shapes.append({"type": "rect", "xref": "paper", "x0": 0, "x1": 1, "y0": t["trz_range"][0],
                            "y1": t["trz_range"][1], "fillcolor": "#5fa8d3", "opacity": 0.15, "line": {"width": 0}})
        annotations.append({"xref": "paper", "x": 0.02, "y": sum(t["trz_range"]) / 2, "text": "Thermal reserve zone",
                            "showarrow": False, "xanchor": "left", "font": {"color": "#5fa8d3"}})
    hearth = [[0, inp["t_hm"]], [geo.z_tuyere, inp["t_hm"]]]
    axial = chart("axial", "Axial temperature profile (1-D)", [
        {"type": "scatter", "x": [round(p[1], 1) for p in prof], "y": zs, "name": "Gas Tg", "mode": "lines",
         "line": {"color": "#ff5a1f", "width": 3}},
        {"type": "scatter", "x": [round(p[2], 1) for p in prof], "y": zs, "name": "Solids Ts", "mode": "lines",
         "line": {"color": "#5fa8d3", "width": 3}},
        {"type": "scatter", "x": [h[1] for h in hearth], "y": [h[0] for h in hearth], "name": "Liquids (hearth)",
         "mode": "lines", "line": {"color": "#c9a227", "width": 3, "dash": "dot"}},
    ], {"height": 560, "xaxis": {"title": "Temperature (°C)"}, "yaxis": {"title": "Height above hearth floor (m)"},
        "shapes": zone_shapes, "annotations": annotations})

    xs, zg, field = temperature_field(inp, ctx)
    contour = chart("field", "Temperature field in the vertical section (solids, °C)", [{
        "type": "contour", "x": [round(x, 2) for x in xs], "y": [round(z, 2) for z in zg], "z": field,
        "colorscale": FURNACE_COLORSCALE, "zmin": 0, "zmax": 2100, "connectgaps": False,
        "contours": {"start": 200, "end": 2200, "size": 200, "showlabels": True,
                     "labelfont": {"size": 10, "color": "white"}},
        "colorbar": {"title": "°C"}, "line": {"width": 0.5, "color": "rgba(255,255,255,0.35)"},
    }, {
        "type": "contour", "x": [round(x, 2) for x in xs], "y": [round(z, 2) for z in zg], "z": field,
        "showscale": False, "contours": {"coloring": "none", "start": inp["t_soft"], "end": inp["t_melt"],
                                         "size": inp["t_melt"] - inp["t_soft"]},
        "line": {"width": 3, "color": "#7CFC9A", "dash": "dash"}, "name": "Cohesive zone", "hoverinfo": "skip",
    }], {"height": 620, "xaxis": {"title": "Radius (m)", "scaleanchor": "y"}, "yaxis": {"title": "Height (m)"}},
        note="Dashed green lines bound the cohesive zone (softening → melting isotherms).")

    rows = []
    for zn in geo.zones:
        zm = 0.5 * (zn["z0"] + zn["z1"])
        if zn["name"] == "Hearth":
            rows.append([zn["name"], zm, inp["t_hm"], inp["t_hm"], "Liquid iron & slag, deadman coke"])
            continue
        Tg, Ts = _interp(prof, zm, 1), _interp(prof, zm, 2)
        rows.append([zn["name"], zm, Tg, Ts, _state(Ts, inp)])
    rows.insert(1, ["Raceway / tuyeres", geo.z_tuyere, ctx["energy_balance"]["T_raft"], prof[0][2], "Combustion zone"])
    warnings = []
    if abs(t["T_top_pred"] - inp["t_top"]) > 60:
        warnings.append(f"Predicted top gas temperature ({t['T_top_pred']:.0f} °C) differs from the value used in "
                        f"the energy balance ({inp['t_top']:.0f} °C). Adjust h_v or the top gas temperature input.")
    return {
        "kpis": [
            kpi("RAFT (gas at tuyeres)", prof[0][1], "°C", 0),
            kpi("Predicted top gas T", t["T_top_pred"], "°C", 0, f"Energy balance input {inp['t_top']:.0f} °C"),
            kpi("Thermal reserve zone T", t["trz_T"] or 0.0, "°C", 0, "Typical 850-1000 °C"),
            kpi("TRZ height range", f"{t['trz_range'][0]:.1f}–{t['trz_range'][1]:.1f}" if t["trz_range"] else "n/a", "m"),
            kpi("Cohesive zone (axis-avg.)",
                f"{t['z_melt']:.1f}–{t['z_soft']:.1f}" if t["z_soft"] and t["z_melt"] else "n/a", "m"),
            kpi("Solids T at tuyere level", prof[0][2], "°C", 0),
            kpi("Heat-capacity ratio (top)", t["W_ratio_top"], "Ws/Wg", 2, "Upper-zone thermal ratio"),
        ],
        "charts": [axial, contour],
        "tables": [table("Temperature by zone (mid-height)", ["Zone", "z (m)", "Gas T (°C)", "Solid T (°C)", "State"],
                         rows, 1)],
        "warnings": warnings,
    }


def _state(Ts, inp):
    if Ts < 200:
        return "Drying / preheating"
    if Ts < 900:
        return "Granular — indirect reduction"
    if Ts < inp["t_soft"]:
        return "Thermal reserve / solution loss"
    if Ts < inp["t_melt"]:
        return "Cohesive (softening–melting)"
    return "Dripping zone (active coke)"


SECTION = Section("temperature", "Temperature Distribution",
                  "Axial gas & solid temperatures from a counter-current heat-exchange model, plus a 2-D field.",
                  compute, report, INPUTS, icon="thermo")
