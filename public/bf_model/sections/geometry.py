"""Furnace geometry: inner profile, zone boundaries and volumes.

Vertical coordinate z is measured upwards from the hearth floor (m).
Tuyere level = top of the hearth.
"""

import math

from ..core.schema import Field, Group, Section, kpi, table, chart

INPUTS = [
    Group("geometry", "Furnace Geometry", [
        Field("d_hearth", "Hearth diameter", "m", 12.0, 4, 20, 0.1),
        Field("h_hearth", "Hearth height (floor to tuyeres)", "m", 4.5, 1.5, 8, 0.1),
        Field("h_bosh", "Bosh height", "m", 3.6, 1, 6, 0.1),
        Field("d_belly", "Belly diameter", "m", 13.6, 5, 22, 0.1),
        Field("h_belly", "Belly height", "m", 2.2, 0.5, 5, 0.1),
        Field("h_stack", "Stack height", "m", 17.0, 8, 25, 0.1),
        Field("d_throat", "Throat diameter", "m", 9.2, 3, 15, 0.1),
        Field("h_throat", "Throat height", "m", 2.0, 0.5, 4, 0.1),
        Field("stockline", "Stockline depth below throat top", "m", 1.0, 0, 3, 0.1),
    ], "Inner refractory profile. Drives the furnace drawing, volumes and the thermal model.", True),
]

ZONE_COLORS = {
    "Hearth": "#7a2e12", "Bosh": "#b5481c", "Belly": "#d0782a", "Stack": "#8c7a5b", "Throat": "#5b6b7a",
}


class Geometry:
    def __init__(self, inp):
        self.rh = inp["d_hearth"] / 2
        self.rb = inp["d_belly"] / 2
        self.rt = inp["d_throat"] / 2
        z = 0.0
        self.zones = []
        for name, h in [("Hearth", inp["h_hearth"]), ("Bosh", inp["h_bosh"]), ("Belly", inp["h_belly"]),
                        ("Stack", inp["h_stack"]), ("Throat", inp["h_throat"])]:
            self.zones.append({"name": name, "z0": z, "z1": z + h})
            z += h
        self.z_top = z
        self.z_tuyere = inp["h_hearth"]
        self.z_stockline = z - inp["stockline"]

    def radius(self, z):
        for zn in self.zones:
            if z <= zn["z1"] + 1e-9:
                f = (z - zn["z0"]) / max(zn["z1"] - zn["z0"], 1e-9)
                n = zn["name"]
                if n == "Hearth":
                    return self.rh
                if n == "Bosh":
                    return self.rh + (self.rb - self.rh) * f
                if n == "Belly":
                    return self.rb
                if n == "Stack":
                    return self.rb + (self.rt - self.rb) * f
                return self.rt
        return self.rt

    def area(self, z):
        return math.pi * self.radius(z) ** 2

    def zone_of(self, z):
        for zn in self.zones:
            if z <= zn["z1"] + 1e-9:
                return zn["name"]
        return "Throat"

    def volume(self, z0, z1, n=400):
        dz = (z1 - z0) / n
        return sum(self.area(z0 + (i + 0.5) * dz) for i in range(n)) * dz

    def profile(self):
        pts = [(0.0, self.rh)]
        for zn in self.zones:
            pts.append((zn["z1"], self.radius(zn["z1"])))
        return pts


def compute(inp, ctx):
    g = Geometry(inp)
    return {
        "geo": g,
        "V_inner": g.volume(0, g.z_top),
        "V_working": g.volume(g.z_tuyere, g.z_stockline),
        "H_working": g.z_stockline - g.z_tuyere,
        "bosh_angle": math.degrees(math.atan2(inp["h_bosh"], g.rb - g.rh)) if g.rb > g.rh else 90.0,
        "stack_angle": math.degrees(math.atan2(inp["h_stack"], g.rb - g.rt)) if g.rb > g.rt else 90.0,
    }


def report(inp, ctx):
    r = ctx["geometry"]
    g = r["geo"]
    rows = [[zn["name"], zn["z0"], zn["z1"], zn["z1"] - zn["z0"], 2 * g.radius(zn["z0"]), 2 * g.radius(zn["z1"]),
             g.volume(zn["z0"], zn["z1"])] for zn in g.zones]
    prof = g.profile()
    xs = [p[1] for p in prof] + [-p[1] for p in reversed(prof)] + [prof[0][1]]
    ys = [p[0] for p in prof] + [p[0] for p in reversed(prof)] + [prof[0][0]]
    return {
        "kpis": [
            kpi("Inner volume", r["V_inner"], "m³", 0),
            kpi("Working volume", r["V_working"], "m³", 0, "Tuyere level to stockline"),
            kpi("Working height", r["H_working"], "m", 1),
            kpi("Bosh angle", r["bosh_angle"], "°", 1, "Typical 78-82°"),
            kpi("Stack angle", r["stack_angle"], "°", 1, "Typical 80-86°"),
        ],
        "tables": [table("Zone dimensions", ["Zone", "z bottom (m)", "z top (m)", "Height (m)",
                                             "D bottom (m)", "D top (m)", "Volume (m³)"], rows)],
        "charts": [chart("profile", "Inner profile (vertical section)", [
            {"type": "scatter", "x": xs, "y": ys, "fill": "toself", "mode": "lines",
             "line": {"color": "#f08a24"}, "fillcolor": "rgba(240,138,36,0.12)", "name": "Inner profile"},
            {"type": "scatter", "x": [-g.rh * 1.25, g.rh * 1.25], "y": [g.z_tuyere] * 2, "mode": "lines",
             "line": {"dash": "dot", "color": "#e24a33"}, "name": "Tuyere level"},
            {"type": "scatter", "x": [-g.rt, g.rt], "y": [g.z_stockline] * 2, "mode": "lines",
             "line": {"dash": "dot", "color": "#8fb3d9"}, "name": "Stockline"},
        ], {"xaxis": {"title": "Radius (m)", "scaleanchor": "y"}, "yaxis": {"title": "Height above hearth floor (m)"}})],
        "warnings": [],
    }


SECTION = Section("geometry", "Furnace Geometry", "Inner profile, zone dimensions and volumes.",
                  compute, report, INPUTS, icon="ruler")
