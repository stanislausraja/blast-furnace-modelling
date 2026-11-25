"""Thermodynamic helper functions (sensible enthalpies, heat capacities)."""

from .constants import CP_GAS, T0


def cp_gas(species, T_K):
    """Molar heat capacity of a gas species, J/mol/K."""
    a, b, c = CP_GAS[species]
    return a + b * T_K + c / (T_K * T_K)


def h_gas(species, T_C):
    """Sensible enthalpy H(T) - H(298 K) of a gas species, kJ/mol. T in degC."""
    T = T_C + 273.15
    a, b, c = CP_GAS[species]
    return (a * (T - T0) + 0.5 * b * (T * T - T0 * T0) - c * (1.0 / T - 1.0 / T0)) / 1000.0


def h_mix(moles, T_C):
    """Sensible enthalpy of a gas mixture, kJ. `moles` = {species: mol}."""
    return sum(n * h_gas(sp, T_C) for sp, n in moles.items() if n)


def cp_mix(moles, T_C):
    """Heat capacity flow of a gas mixture, J/K per unit of `moles` basis."""
    T = T_C + 273.15
    return sum(n * cp_gas(sp, T) for sp, n in moles.items() if n)


def h_hot_metal(T_C):
    """Specific enthalpy of liquid hot metal relative to 25 degC, kJ/kg.

    Linearised around typical tapping temperatures (~1.15 MJ/kg at 1450 degC).
    """
    return 1150.0 + 0.85 * (T_C - 1450.0)


def h_slag(T_C):
    """Specific enthalpy of liquid BF slag relative to 25 degC, kJ/kg (~1.70 MJ/kg at 1500 degC)."""
    return 1700.0 + 1.25 * (T_C - 1500.0)


def cp_solid_burden(T_C):
    """Mean heat capacity of the granular burden (ore + coke), kJ/kg/K."""
    return 0.80 + 0.00035 * T_C


def solve_temperature(h_target, h_of_T, lo=25.0, hi=3500.0, tol=0.05):
    """Find T (degC) such that h_of_T(T) == h_target, by bisection."""
    f_lo = h_of_T(lo) - h_target
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        f_mid = h_of_T(mid) - h_target
        if (f_mid > 0) == (f_lo > 0):
            lo, f_lo = mid, f_mid
        else:
            hi = mid
        if hi - lo < tol:
            break
    return 0.5 * (lo + hi)
