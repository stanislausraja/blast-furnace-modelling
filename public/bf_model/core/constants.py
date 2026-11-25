"""Physical constants and thermochemical data used by all model sections.

All enthalpies in kJ/mol, molar masses in kg/kmol (= g/mol).
Reference state: 25 degC (298.15 K), 1 atm.
"""

T0 = 298.15          # reference temperature, K
NM3_PER_KMOL = 22.414  # normal cubic metres per kmol of ideal gas (0 degC, 1 atm)

# ---------------------------------------------------------------- molar masses
M = {
    "Fe": 55.845, "C": 12.011, "O": 15.999, "H": 1.008, "N": 14.007, "S": 32.06,
    "Si": 28.086, "Mn": 54.938, "P": 30.974, "Ca": 40.078, "Mg": 24.305, "Al": 26.982,
}
M.update({
    "Fe2O3": 2 * M["Fe"] + 3 * M["O"],
    "FeO": M["Fe"] + M["O"],
    "SiO2": M["Si"] + 2 * M["O"],
    "MnO": M["Mn"] + M["O"],
    "P2O5": 2 * M["P"] + 5 * M["O"],
    "CaO": M["Ca"] + M["O"],
    "MgO": M["Mg"] + M["O"],
    "Al2O3": 2 * M["Al"] + 3 * M["O"],
    "CaCO3": M["Ca"] + M["C"] + 3 * M["O"],
    "CO": M["C"] + M["O"],
    "CO2": M["C"] + 2 * M["O"],
    "H2": 2 * M["H"],
    "H2O": 2 * M["H"] + M["O"],
    "N2": 2 * M["N"],
    "O2": 2 * M["O"],
})

# --------------------------------------------- standard enthalpy of formation
# kJ/mol at 298 K (NIST / JANAF rounded)
HF = {
    "CO": -110.53, "CO2": -393.51, "H2O_g": -241.83, "H2O_l": -285.83,
    "Fe2O3": -824.2, "FeO": -272.0, "SiO2": -910.7, "MnO": -385.2,
    "P2O5": -1504.9, "CaCO3": -1207.6, "CaO": -635.1,
}

# --------------------------------------- heat capacity (Kelley form, J/mol/K)
# cp = a + b*T + c/T^2  (T in K), valid ~298-2500 K (Gaskell, Intro. Thermo. of Materials)
CP_GAS = {
    "N2":  (27.87, 4.27e-3, 0.0),
    "O2":  (29.96, 4.18e-3, -1.67e5),
    "CO":  (28.41, 4.10e-3, -0.46e5),
    "CO2": (44.14, 9.04e-3, -8.54e5),
    "H2":  (27.28, 3.26e-3, 0.50e5),
    "H2O": (30.00, 10.71e-3, 0.33e5),
}

# Fixed composition assumptions (wt %) that are rarely changed by the user.
ASH_COMPOSITION = {"SiO2": 50.0, "Al2O3": 30.0, "Fe2O3": 8.0, "CaO": 5.0, "MgO": 2.0, "other": 5.0}
DUST_COMPOSITION = {"C": 35.0, "Fe2O3": 45.0, "CaO": 8.0, "SiO2": 7.0, "Al2O3": 3.0, "MgO": 2.0}
LIMESTONE_COMPOSITION = {"CaCO3": 95.0, "SiO2": 2.0, "MgO": 1.5, "other": 1.5}

AIR_O2 = 0.21  # mole fraction O2 in dry air (Ar lumped with N2)
