"""Overall energy (enthalpy) balance and raceway adiabatic flame temperature (RAFT).

Hess-law balance with reference state 25 degC. Reaction heats use standard
enthalpies of formation; fuels are treated as their elements (their small
heat of formation is lumped into the PCI decomposition heat). Heat losses
(stave/cooling water + shell) are the closing term.
"""

from ..core.constants import M, HF, NM3_PER_KMOL
from ..core.schema import Field, Group, Section, kpi, table, chart, in_range
from ..core.thermo import h_gas, h_mix, h_hot_metal, h_slag, solve_temperature

INPUTS = [
    Group("thermal", "Thermal Conditions", [
        Field("t_blast", "Hot blast temperature", "°C", 1150.0, 600, 1350, 5),
        Field("t_top", "Top gas temperature", "°C", 150.0, 60, 400, 5),
        Field("t_hm", "Hot metal tapping temperature", "°C", 1500.0, 1350, 1600, 5),
        Field("t_slag", "Slag tapping temperature", "°C", 1530.0, 1380, 1650, 5),
        Field("t_coke_raceway", "Coke temperature entering raceway", "°C", 1500.0, 1200, 1700, 10),
        Field("pci_crack", "PCI decomposition heat", "kJ/kg", 900.0, 0, 2500, 10,
              "Heat to devolatilise and crack the coal (higher for high-volatile coal)"),
    ], "Temperatures used by the enthalpy balance and the RAFT calculation."),
]

CP_COKE = 1.65  # kJ/kg/K, mean 25-1500 degC


def raft(inp, mb):
    """Raceway adiabatic flame temperature, degC."""
    n_pci_H2 = mb["pci"]["H"] / M["H"] / 2
    n_H2O = mb["n_H2O_blast"]
    n_pci_water = mb["pci"]["water"] / M["H2O"]
    n_blast_moist = n_H2O - n_pci_water
    blast = {"O2": mb["n_O2"], "N2": mb["n_N2_blast"], "H2O": n_blast_moist}
    C = mb["C_tuyere"]
    C_pci = min(mb["pci"]["C"] / M["C"], C)
    C_coke = C - C_pci
    heat = (h_mix(blast, inp["t_blast"]) * 1000                     # kJ/h (kmol * kJ/mol * 1000)
            + C_coke * M["C"] * CP_COKE * (inp["t_coke_raceway"] - 25)
            - HF["CO"] * C * 1000
            + HF["H2O_g"] * n_blast_moist * 1000
            + HF["H2O_l"] * n_pci_water * 1000
            - mb["pci"]["dry"] * inp["pci_crack"])
    products = {"CO": C, "H2": n_H2O + n_pci_H2, "N2": mb["n_N2_blast"] + mb["pci"]["N"] / M["N2"]}
    T = solve_temperature(heat, lambda T: h_mix(products, T) * 1000)
    return T, products, heat


def compute(inp, ctx):
    mb = ctx["mass_balance"]
    k = 1000.0  # kmol*kJ/mol -> kJ
    g = mb["gas"]
    warnings = []

    blast = {"O2": mb["n_O2"], "N2": mb["n_N2_blast"], "H2O": mb["n_H2O_blast"] - mb["pci"]["water"] / M["H2O"]}
    n_CO2_comb = g["CO2"] - mb["n_caco3"]

    supply = [
        ("Sensible heat of hot blast", h_mix(blast, inp["t_blast"]) * k),
        ("C → CO (combustion + solution loss)", -HF["CO"] * g["CO"] * k),
        ("C → CO₂ (indirect reduction)", -HF["CO2"] * n_CO2_comb * k),
        ("H₂ → H₂O (indirect reduction)", -HF["H2O_g"] * mb["n_H2O_red"] * k),
    ]
    n_moist_l = mb["n_H2O_charge"]
    demand = [
        ("Fe₂O₃ dissociation", -HF["Fe2O3"] * mb["n_fe2o3"] * k),
        ("FeO dissociation (net of FeO to slag)", -HF["FeO"] * (mb["n_feo"] - mb["n_feo_slag"]) * k),
        ("Si, Mn, P reduction", (-HF["SiO2"] * mb["n_Si"] - HF["MnO"] * mb["n_Mn"]
                                 - HF["P2O5"] * mb["n_P"] / 2) * k),
        ("Blast & PCI moisture decomposition", (-HF["H2O_g"] * blast["H2O"]
                                                - HF["H2O_l"] * mb["pci"]["water"] / M["H2O"]) * k),
        ("Limestone calcination", (HF["CaO"] + HF["CO2"] - HF["CaCO3"]) * mb["n_caco3"] * k),
        ("Evaporation of charge moisture", (HF["H2O_g"] - HF["H2O_l"]) * n_moist_l * k),
        ("PCI decomposition", mb["pci"]["dry"] * inp["pci_crack"]),
        ("Sensible heat of hot metal", mb["hm"] * h_hot_metal(inp["t_hm"])),
        ("Sensible heat of slag", mb["m_slag"] * h_slag(inp["t_slag"])),
        ("Sensible heat of top gas", h_mix(g, inp["t_top"]) * k),
        ("Sensible heat of dust", mb["dust"] * 0.9 * (inp["t_top"] - 25)),
    ]
    Q_in = sum(v for _, v in supply)
    Q_used = sum(v for _, v in demand)
    Q_loss = Q_in - Q_used
    if Q_loss < 0:
        warnings.append("Heat demand exceeds supply (negative heat loss): the furnace would cool down. "
                        "Increase fuel rate or blast temperature.")
    T_raft, raceway_gas, _ = raft(inp, mb)
    if not 1900 <= T_raft <= 2400:
        warnings.append(f"RAFT {T_raft:.0f} °C is outside the usual 1900–2400 °C operating window.")
    # heat that the solids must absorb for direct reduction & melting (used by the thermal model)
    Q_dr = ((-HF["FeO"] + HF["CO"]) * mb["O_dir_Fe"]
            + (-HF["SiO2"] + 2 * HF["CO"]) * mb["n_Si"] + (-HF["MnO"] + HF["CO"]) * mb["n_Mn"]
            + (-HF["P2O5"] / 2 + 2.5 * HF["CO"]) * mb["n_P"]) * k
    return {"supply": supply, "demand": demand, "Q_in": Q_in, "Q_used": Q_used, "Q_loss": Q_loss,
            "T_raft": T_raft, "raceway_gas": raceway_gas, "Q_dr": Q_dr,
            "Q_calc": (HF["CaO"] + HF["CO2"] - HF["CaCO3"]) * mb["n_caco3"] * k,
            "Q_evap": (HF["H2O_g"] - HF["H2O_l"]) * n_moist_l * k, "warnings": warnings}


def report(inp, ctx):
    e = ctx["energy_balance"]
    mb = ctx["mass_balance"]
    per_t = 1000.0 / mb["hm"]
    GJ = lambda kj: kj / 1e6
    loss_pct = e["Q_loss"] / e["Q_in"] * 100
    n_bosh = sum(e["raceway_gas"].values())
    rg_pct = {k: v / n_bosh * 100 for k, v in e["raceway_gas"].items()}
    rows = [["SUPPLY", "", "", ""]]
    rows += [[n, GJ(v), GJ(v) * per_t, v / e["Q_in"] * 100] for n, v in e["supply"]]
    rows += [["Total supply", GJ(e["Q_in"]), GJ(e["Q_in"]) * per_t, 100.0], ["DEMAND", "", "", ""]]
    rows += [[n, GJ(v), GJ(v) * per_t, v / e["Q_in"] * 100] for n, v in e["demand"]]
    rows += [["Heat losses (closing term)", GJ(e["Q_loss"]), GJ(e["Q_loss"]) * per_t, loss_pct],
             ["Total demand", GJ(e["Q_in"]), GJ(e["Q_in"]) * per_t, 100.0]]

    names = [n for n, _ in e["supply"]] + [n for n, _ in e["demand"]] + ["Heat losses"]
    vals = [GJ(v) * per_t for _, v in e["supply"]] + [-GJ(v) * per_t for _, v in e["demand"]] + [-GJ(e["Q_loss"]) * per_t]
    waterfall = chart("waterfall", "Heat flow per tonne hot metal (GJ/tHM)", [{
        "type": "waterfall", "orientation": "v", "x": names, "y": [round(v, 3) for v in vals],
        "measure": ["relative"] * len(vals),
        "increasing": {"marker": {"color": "#f08a24"}}, "decreasing": {"marker": {"color": "#5fa8d3"}},
        "connector": {"line": {"color": "rgba(150,150,150,0.4)"}},
    }], {"height": 460, "xaxis": {"tickangle": -35}, "yaxis": {"title": "GJ/tHM"}, "margin": {"b": 170}})
    donut = chart("demand", "Where the heat goes", [{
        "type": "pie", "hole": 0.55,
        "labels": [n for n, _ in e["demand"]] + ["Heat losses"],
        "values": [round(GJ(v) * per_t, 3) for _, v in e["demand"]] + [round(max(GJ(e["Q_loss"]) * per_t, 0), 3)],
        "textinfo": "percent",
    }], {"height": 380, "showlegend": True})

    return {
        "kpis": [
            kpi("Total heat supply", GJ(e["Q_in"]) * per_t, "GJ/tHM", 2, f"{GJ(e['Q_in']):,.0f} GJ/h"),
            kpi("Heat losses", GJ(e["Q_loss"]) * per_t, "GJ/tHM", 2, f"{loss_pct:.1f} % of supply (typ. 4-10 %)",
                in_range(loss_pct, 3, 12)),
            kpi("RAFT", e["T_raft"], "°C", 0, "Raceway adiabatic flame temperature", in_range(e["T_raft"], 2000, 2350)),
            kpi("Bosh gas volume", n_bosh * NM3_PER_KMOL * per_t, "Nm³/tHM", 0),
            kpi("Bosh gas CO", rg_pct["CO"], "vol %", 1),
            kpi("Bosh gas H₂", rg_pct["H2"], "vol %", 1),
            kpi("Hot metal enthalpy", h_hot_metal(inp["t_hm"]) / 1000, "GJ/tHM", 3),
            kpi("Top gas sensible heat", GJ(dict(e["demand"])["Sensible heat of top gas"]) * per_t, "GJ/tHM", 2),
        ],
        "equations": [{
            "title": "Overall enthalpy balance", "unit": "GJ/tHM",
            "terms": [
                {"name": "Q supply", "items": [[n, GJ(v) * per_t] for n, v in e["supply"]]},
                {"name": "Q demand", "items": [[n, GJ(v) * per_t] for n, v in e["demand"]], "side": "out"},
                {"name": "Q loss", "items": [["Cooling & shell losses", GJ(e["Q_loss"]) * per_t]], "side": "out"},
            ],
            "lhs_total": GJ(e["Q_in"]) * per_t, "rhs_total": GJ(e["Q_used"] + e["Q_loss"]) * per_t,
        }],
        "charts": [waterfall, donut],
        "tables": [
            table("Enthalpy balance (reference 25 °C)", ["Item", "GJ/h", "GJ/tHM", "% of supply"], rows, 3),
            table("Raceway (bosh) gas", ["Species", "vol %", "Nm³/tHM"],
                  [[k, rg_pct[k], v * NM3_PER_KMOL * per_t] for k, v in e["raceway_gas"].items()]),
        ],
        "warnings": e["warnings"],
    }


SECTION = Section("energy_balance", "Energy Balance",
                  "Hess-law enthalpy balance per tonne of hot metal, heat losses and RAFT.",
                  compute, report, INPUTS, icon="flame")
