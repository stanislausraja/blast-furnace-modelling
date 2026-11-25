"""Overall mass balance (steady state, element-by-element).

    m_charge (sinter + pellet + lump ore + coke + flux) + m_blast (air + O2 + PCI)
        = m_tap (hot metal + slag) + m_gas (top gas + dust)

Hot-metal production is NOT an input: it follows from the iron balance.
Top-gas composition follows from the C, O, H and N balances, with the
hydrogen utilisation eta_H2 as the only gas-side closure parameter.
"""

from ..core.constants import (M, NM3_PER_KMOL, AIR_O2, ASH_COMPOSITION, DUST_COMPOSITION,
                              LIMESTONE_COMPOSITION)
from ..core.schema import Field, Group, Section, kpi, table, chart, in_range

ORES = [("sinter", "Sinter"), ("pellet", "Pellet"), ("lump", "Lump ore")]
ORE_DEFAULTS = {
    #          Fe    FeO  SiO2  Al2O3 CaO  MgO  MnO  P2O5  H2O
    "sinter": (57.5, 8.0, 5.2, 1.8, 9.0, 1.6, 0.30, 0.13, 0.0),
    "pellet": (65.0, 0.5, 3.5, 0.6, 0.8, 0.5, 0.10, 0.04, 1.5),
    "lump":   (62.5, 0.3, 4.0, 2.2, 0.1, 0.1, 0.20, 0.12, 3.0),
}
ORE_FIELDS = [("fe", "Fe total"), ("feo", "FeO"), ("sio2", "SiO2"), ("al2o3", "Al2O3"), ("cao", "CaO"),
              ("mgo", "MgO"), ("mno", "MnO"), ("p2o5", "P2O5"), ("h2o", "Moisture (wet basis)")]


def _ore_group(key, name):
    d = ORE_DEFAULTS[key]
    return Group(f"chem_{key}", f"{name} Chemistry", [
        Field(f"{key}_{f}", lbl, "wt%", d[i], 0, 100, 0.01,
              "Dry basis" if f != "h2o" else "Free moisture, wet basis")
        for i, (f, lbl) in enumerate(ORE_FIELDS)
    ], "Remainder to 100 % (LOI, alkalis, TiO2 ...) is reported to slag as 'other'.", True)


def _fuel_group(key, name, d):
    return Group(f"chem_{key}", f"{name} Ultimate Analysis", [
        Field(f"{key}_c", "Carbon", "wt%", d[0], 0, 100, 0.1, "Dry basis"),
        Field(f"{key}_h", "Hydrogen", "wt%", d[1], 0, 10, 0.05, "Dry basis"),
        Field(f"{key}_n", "Nitrogen", "wt%", d[2], 0, 5, 0.05, "Dry basis"),
        Field(f"{key}_s", "Sulphur", "wt%", d[3], 0, 3, 0.01, "Dry basis"),
        Field(f"{key}_ash", "Ash", "wt%", d[4], 0, 30, 0.1, "Dry basis"),
        Field(f"{key}_h2o", "Moisture (wet basis)", "wt%", d[5], 0, 20, 0.1),
    ], "Oxygen = 100 − (C + H + N + S + ash), dry basis.", True)


INPUTS = [
    Group("charge", "Charge (Top Burden)", [
        Field("m_sinter", "Sinter", "t/h", 295.0, 0, 1000, 1),
        Field("m_pellet", "Pellet", "t/h", 80.0, 0, 1000, 1),
        Field("m_lump", "Lump ore", "t/h", 27.5, 0, 500, 0.5),
        Field("m_coke", "Coke (wet)", "t/h", 91.0, 1, 300, 0.5),
        Field("m_limestone", "Limestone flux", "t/h", 0.0, 0, 100, 0.5),
    ], "Mass flows charged through the top (as received)."),
    Group("blast", "Blast & Tuyere Injection", [
        Field("v_air", "Cold blast air", "Nm³/h", 250000.0, 10000, 600000, 1000),
        Field("v_o2", "Oxygen enrichment", "Nm³/h", 12000.0, 0, 100000, 500),
        Field("o2_purity", "Oxygen purity", "vol%", 99.5, 80, 100, 0.1),
        Field("humidity", "Blast moisture", "g/Nm³", 20.0, 0, 60, 1, "Per Nm³ of dry air"),
        Field("m_pci", "Pulverised coal injection (PCI)", "t/h", 40.0, 0, 120, 0.5),
    ], "Everything entering through the tuyeres."),
    *[_ore_group(k, n) for k, n in ORES],
    _fuel_group("coke", "Coke", (87.5, 0.3, 1.0, 0.6, 10.1, 3.0)),
    _fuel_group("pci", "PCI Coal", (80.0, 4.5, 1.5, 0.5, 9.5, 1.0)),
    Group("products", "Hot Metal & Distribution", [
        Field("hm_c", "Hot metal C", "wt%", 4.6, 3, 5.5, 0.05),
        Field("hm_si", "Hot metal Si", "wt%", 0.45, 0, 2, 0.01),
        Field("hm_mn", "Hot metal Mn", "wt%", 0.30, 0, 2, 0.01),
        Field("hm_p", "Hot metal P", "wt%", 0.07, 0, 1, 0.005),
        Field("hm_s", "Hot metal S", "wt%", 0.03, 0, 0.2, 0.005),
        Field("fe_to_slag", "Fe loss to slag (as FeO)", "% of Fe in", 0.4, 0, 5, 0.05),
        Field("dust_rate", "Top dust (flue dust + sludge)", "kg/tHM", 15.0, 0, 60, 0.5),
        Field("eta_h2", "Hydrogen utilisation ηH₂", "%", 40.0, 0, 80, 1,
              "Share of H₂ converted to H₂O by reducing iron oxides"),
    ], "Hot metal analysis is a target; the remainder of each element reports to slag.", True),
]


def _split_fuel(prefix, wet, inp):
    dry = wet * (1 - inp[f"{prefix}_h2o"] / 100)
    c, h, n, s, ash = (inp[f"{prefix}_{k}"] / 100 * dry for k in ("c", "h", "n", "s", "ash"))
    o = max(dry - c - h - n - s - ash, 0.0)
    return {"wet": wet, "dry": dry, "water": wet - dry, "C": c, "H": h, "N": n, "S": s, "ash": ash, "O": o}


def compute(inp, ctx):
    warnings = []
    t = 1000.0  # t -> kg
    pool = {k: 0.0 for k in ("Fe2O3", "FeO", "SiO2", "Al2O3", "CaO", "MgO", "MnO", "P2O5", "other",
                             "C", "H", "N", "S", "O_fuel", "CaCO3", "H2O_top")}
    charge_detail = []

    # ---------------------------------------------------------------- ores
    for key, name in ORES:
        wet = inp[f"m_{key}"] * t
        dry = wet * (1 - inp[f"{key}_h2o"] / 100)
        fe, feo = inp[f"{key}_fe"] / 100 * dry, inp[f"{key}_feo"] / 100 * dry
        fe3 = fe - feo * M["Fe"] / M["FeO"]
        if fe3 < -1e-6:
            warnings.append(f"{name}: FeO is higher than total Fe allows; Fe³⁺ clipped to zero.")
        fe2o3 = max(fe3, 0) * M["Fe2O3"] / (2 * M["Fe"])
        comp = {"Fe2O3": fe2o3, "FeO": feo}
        for sp in ("SiO2", "Al2O3", "CaO", "MgO", "MnO", "P2O5"):
            comp[sp] = inp[f"{key}_{sp.lower()}"] / 100 * dry
        other = dry - sum(comp.values())
        if other < -1e-6 and dry > 0:
            warnings.append(f"{name}: analysis sums to more than 100 % ({100 - other / dry * 100:.1f} %).")
        comp["other"] = max(other, 0.0)
        for sp, v in comp.items():
            pool[sp] += v
        pool["H2O_top"] += wet - dry
        charge_detail.append((name, wet, dry, fe, comp))

    # --------------------------------------------------------------- fuels
    coke = _split_fuel("coke", inp["m_coke"] * t, inp)
    pci = _split_fuel("pci", inp["m_pci"] * t, inp)
    for f in (coke, pci):
        for el in ("C", "H", "N", "S"):
            pool[el] += f[el]
        pool["O_fuel"] += f["O"]
        for sp, pct in ASH_COMPOSITION.items():
            pool[sp] += f["ash"] * pct / 100
    pool["H2O_top"] += coke["water"]          # coke moisture evaporates in the throat

    # ----------------------------------------------------------- limestone
    lime = inp["m_limestone"] * t
    for sp, pct in LIMESTONE_COMPOSITION.items():
        pool[sp] += lime * pct / 100

    # -------------------------------------------------------------- blast
    n_air = inp["v_air"] / NM3_PER_KMOL
    n_o2_enr = inp["v_o2"] / NM3_PER_KMOL
    n_O2 = n_air * AIR_O2 + n_o2_enr * inp["o2_purity"] / 100
    n_N2_blast = n_air * (1 - AIR_O2) + n_o2_enr * (1 - inp["o2_purity"] / 100)
    m_moist = inp["humidity"] / 1000 * inp["v_air"]                  # kg/h
    n_H2O_blast = m_moist / M["H2O"] + pci["water"] / M["H2O"]       # PCI moisture decomposes in raceway
    m_blast_gas = n_O2 * M["O2"] + n_N2_blast * M["N2"] + m_moist

    # --------------------------------------------- iron balance (iterative)
    x_fe = 1 - sum(inp[k] for k in ("hm_c", "hm_si", "hm_mn", "hm_p", "hm_s")) / 100
    fe_in = (pool["Fe2O3"] * 2 * M["Fe"] / M["Fe2O3"] + pool["FeO"] * M["Fe"] / M["FeO"])
    hm = fe_in * 0.95 / x_fe
    for _ in range(60):
        dust = inp["dust_rate"] * hm / t
        fe_dust = dust * DUST_COMPOSITION["Fe2O3"] / 100 * 2 * M["Fe"] / M["Fe2O3"]
        fe_slag = inp["fe_to_slag"] / 100 * fe_in
        hm_new = (fe_in - fe_dust - fe_slag) / x_fe
        if abs(hm_new - hm) < 1e-6:
            break
        hm = hm_new
    hm = hm_new
    dust = inp["dust_rate"] * hm / t

    # remove dust from pools (dust is carried out of the burden unreacted)
    dust_comp = {sp: dust * pct / 100 for sp, pct in DUST_COMPOSITION.items()}
    for sp, v in dust_comp.items():
        pool[sp] -= v
    if pool["C"] < 0:
        warnings.append("Dust carbon exceeds carbon input.")

    # elements to hot metal
    hm_el = {el: inp[f"hm_{el.lower()}"] / 100 * hm for el in ("C", "Si", "Mn", "P", "S")}
    hm_el["Fe"] = x_fe * hm
    n = {el: v / M[el] for el, v in hm_el.items()}

    # ------------------------------------------------------------- slag
    m_feo_slag = fe_slag * M["FeO"] / M["Fe"]
    slag = {
        "SiO2": pool["SiO2"] - n["Si"] * M["SiO2"],
        "Al2O3": pool["Al2O3"],
        "CaO": pool["CaO"] + pool["CaCO3"] * M["CaO"] / M["CaCO3"],
        "MgO": pool["MgO"],
        "MnO": pool["MnO"] - n["Mn"] * M["MnO"],
        "FeO": m_feo_slag,
        "P2O5": pool["P2O5"] - n["P"] / 2 * M["P2O5"],
        "S": pool["S"] - hm_el["S"],
        "other": pool["other"],
    }
    for sp, label in (("SiO2", "Si"), ("MnO", "Mn"), ("P2O5", "P"), ("S", "S")):
        if slag[sp] < -1e-6:
            warnings.append(f"Not enough {label} in the charge to meet the hot-metal {label} target "
                            f"(slag {sp} would be negative).")
    m_slag = sum(slag.values())

    # ----------------------------------------------------------- oxygen removed from the burden
    n_fe2o3, n_feo = pool["Fe2O3"] / M["Fe2O3"], pool["FeO"] / M["FeO"]
    O_fe_oxides = 3 * n_fe2o3 + n_feo
    O_fe_removed = O_fe_oxides - m_feo_slag / M["FeO"]
    O_SiMnP = 2 * n["Si"] + n["Mn"] + 2.5 * n["P"]
    O_removed = O_fe_removed + O_SiMnP

    # ------------------------------------------------------------ top gas (kmol/h)
    n_caco3 = pool["CaCO3"] / M["CaCO3"]
    C_gas_fuel = (pool["C"] - hm_el["C"]) / M["C"]
    C_gas = C_gas_fuel + n_caco3
    O_fuel = pool["O_fuel"] / M["O"]
    H2_total = n_H2O_blast + pool["H"] / M["H"] / 2
    n_H2O_red = inp["eta_h2"] / 100 * H2_total
    O_COx = 2 * n_O2 + n_H2O_blast + O_fuel + O_removed - n_H2O_red + 2 * n_caco3
    gas = {
        "CO": 2 * C_gas - O_COx,
        "CO2": O_COx - C_gas,
        "H2": H2_total - n_H2O_red,
        "H2O": n_H2O_red + pool["H2O_top"] / M["H2O"],
        "N2": n_N2_blast + pool["N"] / M["N2"],
    }
    if gas["CO2"] < 0 or gas["CO"] < 0:
        warnings.append("Oxygen/carbon ratio of the top gas is outside CO–CO₂ limits: check fuel rate "
                        "versus blast oxygen.")
    m_gas = sum(v * M[sp] for sp, v in gas.items())

    # ------------------------------------- Rist-type split of the reduction work
    n_O_raceway = 2 * n_O2 + n_H2O_blast + O_fuel       # all burns to CO in front of the tuyeres
    C_tuyere = n_O_raceway
    C_DR = C_gas_fuel - C_tuyere                          # carbon gasified by solution loss / direct reduction
    O_dir_Fe = C_DR - O_SiMnP
    r_d = O_dir_Fe / n["Fe"] if n["Fe"] else 0.0
    if not 0 <= r_d <= 1:
        warnings.append(f"Degree of direct reduction r_d = {r_d:.2f} is outside 0–1: carbon supply and "
                        "blast oxygen are inconsistent.")
    O_ind = O_fe_removed - O_dir_Fe
    pci_C_share = pci["C"] / M["C"] / C_tuyere if C_tuyere else 0.0

    # ----------------------------------------------------------- totals
    m_ore = sum(c[1] for c in charge_detail)
    m_charge = m_ore + coke["wet"] + lime
    m_blast = m_blast_gas + pci["wet"]
    m_in = m_charge + m_blast
    m_out = hm + m_slag + m_gas + dust

    return {
        "warnings": warnings, "charge_detail": charge_detail, "coke": coke, "pci": pci, "lime": lime,
        "hm": hm, "hm_el": hm_el, "x_fe": x_fe, "slag": slag, "m_slag": m_slag, "dust": dust,
        "dust_comp": dust_comp, "gas": gas, "m_gas": m_gas,
        "n_air": n_air, "n_O2": n_O2, "n_N2_blast": n_N2_blast, "n_H2O_blast": n_H2O_blast,
        "m_moist": m_moist, "m_blast_gas": m_blast_gas,
        "m_ore": m_ore, "m_charge": m_charge, "m_blast": m_blast, "m_in": m_in, "m_out": m_out,
        "fe_in": fe_in, "fe_slag": fe_slag, "fe_dust": fe_dust,
        "n_Fe_HM": n["Fe"], "n_Si": n["Si"], "n_Mn": n["Mn"], "n_P": n["P"],
        "n_fe2o3": n_fe2o3, "n_feo": n_feo, "n_feo_slag": m_feo_slag / M["FeO"], "n_caco3": n_caco3,
        "O_fe_removed": O_fe_removed, "O_SiMnP": O_SiMnP, "O_removed": O_removed,
        "O_dir_Fe": O_dir_Fe, "O_ind": O_ind, "n_H2O_red": n_H2O_red, "H2_total": H2_total,
        "C_tuyere": C_tuyere, "C_DR": C_DR, "r_d": r_d, "pci_C_share": pci_C_share,
        "n_H2O_charge": pool["H2O_top"] / M["H2O"], "pool": pool,
        "bosh_gas": {"CO": C_tuyere, "H2": H2_total, "N2": gas["N2"]},
    }


def _pct(d):
    s = sum(v for v in d.values())
    return {k: (v / s * 100 if s else 0) for k, v in d.items()}


def report(inp, ctx):
    r = ctx["mass_balance"]
    geo = ctx.get("geometry")
    hm = r["hm"]
    per_t = 1000.0 / hm            # kg/h -> kg/tHM
    tph = lambda kg: kg / 1000.0   # kg/h -> t/h
    gas_dry = {k: v for k, v in r["gas"].items() if k != "H2O"}
    gas_pct = _pct(gas_dry)
    n_gas_dry = sum(gas_dry.values())
    eta_co = r["gas"]["CO2"] / (r["gas"]["CO"] + r["gas"]["CO2"]) * 100
    coke_rate = r["coke"]["dry"] * per_t
    pci_rate = r["pci"]["dry"] * per_t
    closure = (r["m_in"] - r["m_out"]) / r["m_in"] * 100
    sl = r["slag"]
    b2 = sl["CaO"] / sl["SiO2"] if sl["SiO2"] > 0 else 0
    b4 = (sl["CaO"] + sl["MgO"]) / (sl["SiO2"] + sl["Al2O3"]) if sl["SiO2"] > 0 else 0

    kpis = [
        kpi("Hot metal production", tph(hm), "t/h", 1, f"{tph(hm) * 24:,.0f} t/day"),
        kpi("Slag", tph(r["m_slag"]), "t/h", 1, f"{r['m_slag'] * per_t:.0f} kg/tHM",
            in_range(r["m_slag"] * per_t, 200, 350)),
        kpi("Top gas (dry)", n_gas_dry * NM3_PER_KMOL / 1000, "kNm³/h", 1,
            f"{n_gas_dry * NM3_PER_KMOL * per_t:.0f} Nm³/tHM"),
        kpi("Coke rate (dry)", coke_rate, "kg/tHM", 0, "", in_range(coke_rate, 280, 450)),
        kpi("PCI rate (dry)", pci_rate, "kg/tHM", 0),
        kpi("Fuel rate", coke_rate + pci_rate, "kg/tHM", 0, "Typical 480-530", in_range(coke_rate + pci_rate, 460, 560)),
        kpi("Gas utilisation ηCO", eta_co, "%", 1, "CO₂/(CO+CO₂), typical 45-50", in_range(eta_co, 40, 52)),
        kpi("Direct reduction degree r_d", r["r_d"], "", 3, "Typical 0.25-0.45", in_range(r["r_d"], 0.2, 0.48)),
        kpi("Slag basicity B2", b2, "CaO/SiO₂", 2, "Typical 1.0-1.25", in_range(b2, 0.95, 1.3)),
        kpi("Mass balance closure", closure, "%", 4, "(in − out)/in", "ok" if abs(closure) < 0.01 else "bad"),
    ]
    if geo:
        prod = tph(hm) * 24 / geo["V_working"]
        kpis.insert(1, kpi("Productivity", prod, "t/m³·d", 2, "Working volume basis", in_range(prod, 1.8, 3.0)))

    # ------------------------------------------------------- equation block
    ores = r["charge_detail"]
    lhs = [[d[0], tph(d[1])] for d in ores]
    lhs += [["Coke", tph(r["coke"]["wet"])]]
    if r["lime"]:
        lhs.append(["Limestone", tph(r["lime"])])
    blast = [["Air (dry)", tph(r["n_air"] * (AIR_O2 * M["O2"] + (1 - AIR_O2) * M["N2"]))],
             ["O₂ enrichment", tph(r["m_blast_gas"] - r["m_moist"] - r["n_air"] * (AIR_O2 * M["O2"] + (1 - AIR_O2) * M["N2"]))],
             ["Blast moisture", tph(r["m_moist"])], ["PCI", tph(r["pci"]["wet"])]]
    equations = [{
        "title": "Overall mass balance",
        "unit": "t/h",
        "terms": [
            {"name": "m charge", "items": lhs},
            {"name": "m blast", "items": blast},
            {"name": "M tap", "items": [["Hot metal", tph(hm)], ["Slag", tph(r["m_slag"])]], "side": "out"},
            {"name": "m gas", "items": [["Top gas", tph(r["m_gas"])], ["Dust", tph(r["dust"])]], "side": "out"},
        ],
        "lhs_total": tph(r["m_in"]), "rhs_total": tph(r["m_out"]),
    }]

    # ------------------------------------------------------------- tables
    rows_in = [[n, tph(w), w * per_t, w / r["m_in"] * 100] for n, w, *_ in ores]
    rows_in += [["Coke (wet)", tph(r["coke"]["wet"]), r["coke"]["wet"] * per_t, r["coke"]["wet"] / r["m_in"] * 100]]
    if r["lime"]:
        rows_in.append(["Limestone", tph(r["lime"]), r["lime"] * per_t, r["lime"] / r["m_in"] * 100])
    for name, v in blast:
        rows_in.append([name, v, v * 1000 * per_t, v * 1000 / r["m_in"] * 100])
    rows_in.append(["TOTAL IN", tph(r["m_in"]), r["m_in"] * per_t, 100.0])
    outs = [("Hot metal", hm), ("Slag", r["m_slag"]), ("Top gas (wet)", r["m_gas"]), ("Dust", r["dust"])]
    rows_out = [[n, tph(v), v * per_t, v / r["m_in"] * 100] for n, v in outs]
    rows_out.append(["TOTAL OUT", tph(r["m_out"]), r["m_out"] * per_t, r["m_out"] / r["m_in"] * 100])

    hm_rows = [[el, r["hm_el"][el] / hm * 100, r["hm_el"][el] * per_t] for el in ("Fe", "C", "Si", "Mn", "P", "S")]
    slag_pct = _pct(sl)
    slag_rows = [[sp, slag_pct[sp], v * per_t] for sp, v in sl.items()]
    gas_wet_pct = _pct(r["gas"])
    gas_rows = [[sp, gas_wet_pct[sp], gas_pct.get(sp, 0.0), v * NM3_PER_KMOL * per_t] for sp, v in r["gas"].items()]

    fe_rows = [["Fe charged", r["fe_in"] * per_t], ["→ hot metal", r["hm_el"]["Fe"] * per_t],
               ["→ slag (FeO)", r["fe_slag"] * per_t], ["→ dust", r["fe_dust"] * per_t]]
    C_in = r["pool"]["C"] + r["dust_comp"]["C"]
    c_rows = [["C charged (coke + PCI)", C_in * per_t], ["→ burnt at tuyeres", r["C_tuyere"] * M["C"] * per_t],
              ["→ solution loss / direct reduction", r["C_DR"] * M["C"] * per_t],
              ["→ hot metal", r["hm_el"]["C"] * per_t], ["→ dust", r["dust_comp"]["C"] * per_t]]

    # ---------------------------------------------------------- Sankey
    labels = [n for n, *_ in ores] + ["Coke", "Limestone", "Blast air + O₂", "Moisture", "PCI",
                                      "BLAST FURNACE", "Hot metal", "Slag", "Top gas", "Dust"]
    idx = {l: i for i, l in enumerate(labels)}
    src, tgt, val = [], [], []
    for n, w, *_ in ores:
        src.append(idx[n]); tgt.append(idx["BLAST FURNACE"]); val.append(tph(w))
    for name, v in [("Coke", r["coke"]["wet"]), ("Limestone", r["lime"]),
                    ("Blast air + O₂", r["m_blast_gas"] - r["m_moist"]), ("Moisture", r["m_moist"]),
                    ("PCI", r["pci"]["wet"])]:
        src.append(idx[name]); tgt.append(idx["BLAST FURNACE"]); val.append(tph(v))
    for name, v in outs:
        key = "Top gas" if name.startswith("Top gas") else name
        src.append(idx["BLAST FURNACE"]); tgt.append(idx[key]); val.append(tph(v))
    node_colors = ["#c8553d", "#8c5a3c", "#a0522d", "#3a3a3a", "#d9d9d9", "#5fa8d3", "#87c9f0", "#555555",
                   "#f08a24", "#ff5a1f", "#c9a227", "#8fb3d9", "#9e9e9e"]
    sankey = chart("sankey", "Mass flow (t/h)", [{
        "type": "sankey", "arrangement": "snap",
        "node": {"label": labels, "pad": 18, "thickness": 18, "color": node_colors},
        "link": {"source": src, "target": tgt, "value": val, "color": "rgba(240,138,36,0.25)"},
        "valueformat": ".1f", "valuesuffix": " t/h",
    }], {"height": 420})

    gas_chart = chart("topgas", "Top gas composition (dry, vol %)", [{
        "type": "pie", "labels": list(gas_pct.keys()), "values": [round(v, 2) for v in gas_pct.values()],
        "hole": 0.55, "marker": {"colors": ["#f08a24", "#8c8c8c", "#5fa8d3", "#3f6e9a"]},
    }], {"height": 320})
    slag_chart = chart("slag", "Slag composition (wt %)", [{
        "type": "pie", "labels": list(slag_pct.keys()), "values": [round(v, 2) for v in slag_pct.values()],
        "hole": 0.55,
    }], {"height": 320})

    return {
        "kpis": kpis,
        "equations": equations,
        "charts": [sankey, gas_chart, slag_chart],
        "tables": [
            table("Inputs", ["Stream", "t/h", "kg/tHM", "% of total"], rows_in),
            table("Outputs", ["Stream", "t/h", "kg/tHM", "% of input"], rows_out),
            table("Hot metal composition", ["Element", "wt %", "kg/tHM"], hm_rows, 3),
            table("Slag composition", ["Component", "wt %", "kg/tHM"], slag_rows),
            table("Top gas composition", ["Species", "vol % (wet)", "vol % (dry)", "Nm³/tHM"], gas_rows),
            table("Iron balance", ["Item", "kg/tHM"], fe_rows),
            table("Carbon balance", ["Item", "kg/tHM"], c_rows),
            table("Slag ratios", ["Index", "Value"], [["B2 = CaO/SiO₂", b2], ["B3 = (CaO+MgO)/SiO₂",
                  (sl["CaO"] + sl["MgO"]) / sl["SiO2"] if sl["SiO2"] > 0 else 0], ["B4 = (CaO+MgO)/(SiO₂+Al₂O₃)", b4],
                  ["Al₂O₃ in slag (%)", slag_pct["Al2O3"]]]),
        ],
        "warnings": r["warnings"],
    }


SECTION = Section("mass_balance", "Mass Balance",
                  "Element-by-element steady-state balance: m charge + m blast = M tap + m gas.",
                  compute, report, INPUTS, icon="scale")
