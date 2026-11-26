# Blast Furnace Simulator

Interactive numerical & visual model of an iron-making blast furnace.
The model is written in **pure Python** and runs **inside the browser** (via [Pyodide](https://pyodide.org)),
so the website is fully static — no server, no build step — and deploys identically on **Vercel** or **Netlify**.

| Section | What it computes |
|---|---|
| **Furnace Geometry** | Inner profile, zone heights/diameters, inner & working volume, bosh/stack angles |
| **Mass Balance** | `m charge (sinter + pellet + lump ore + coke) + m blast (air + O₂ + PCI) = M tap (hot metal + slag) + m gas (top gas + dust)` — element by element (Fe, C, O, H, N, Si, Mn, P, S, Ca, Mg, Al); hot-metal output, slag rate & chemistry, top-gas analysis, coke/fuel rate, ηCO, degree of direct reduction r_d |
| **Energy Balance** | Hess-law enthalpy balance (25 °C reference), heat-loss closing term, raceway adiabatic flame temperature (RAFT), bosh gas |
| **Temperature Distribution** | 1-D counter-current gas/solid heat exchange (thermal reserve zone emerges from the reaction heats), 2-D temperature field and cohesive zone |
| **Chemical Composition** | Iron-oxide phases (Fe₂O₃ → Fe₃O₄ → FeO → Fe), gas composition, reduction degree and molten fraction at every height; zone table, products, Rist diagram |

The **Overview** tab draws the furnace from the model output (geometry, isotherms, ore/coke layers, cohesive zone,
dripping zone, raceways, hearth liquids, tuyeres, top) — click a zone to inspect it, hover to read local temperature.

## Project structure

```
public/                     ← the deployed website (static)
  index.html
  assets/css/style.css
  assets/js/app.js          ← UI: forms, tabs, KPIs, equations, charts, tables (generated from the Python schema)
  assets/js/furnace.js      ← interactive SVG furnace drawing
  assets/js/worker.js       ← Web Worker hosting Pyodide + the Python model
  bf_model/                 ← THE MODEL (pure Python, standard library only)
    manifest.json           ← list of .py files the browser loads
    registry.py             ← ordered list of model sections + pipeline
    core/                   ← constants, thermodynamics, schema helpers
    sections/               ← one file per model section
run_model.py                ← run the model from the command line
tests/test_model.py         ← balance-closure & physics tests
vercel.json / netlify.toml  ← deployment config (publish directory = public)
```

## Run locally

```powershell
python -m http.server 8765 --directory public
```
Open http://localhost:8765. (The first visit downloads the Python runtime, ≈ 10 MB, then it is cached.)

Command line / tests:
```powershell
python run_model.py                    # default case
python run_model.py my_inputs.json     # inputs exported from the web page (⋯ → Export inputs)
python -m pytest -q
```

## Deploy

**Vercel:** import the repository (or run `vercel` in this folder). `vercel.json` sets the output directory to `public`; no build command.

**Netlify:** import the repository (or drag the `public` folder into Netlify Drop). `netlify.toml` sets `publish = "public"`.

## Adding / extending a model

1. Create `public/bf_model/sections/my_model.py`:

```python
from ..core.schema import Field, Group, Section, kpi, table, chart

INPUTS = [Group("my_inputs", "My Model Inputs", [
    Field("my_param", "Some parameter", "unit", 1.0, 0, 10, 0.1, "help text"),
])]

def compute(inp, ctx):
    mb = ctx["mass_balance"]            # results of earlier sections are available
    return {"answer": inp["my_param"] * mb["hm"]}

def report(inp, ctx):
    r = ctx["my_model"]
    return {"kpis": [kpi("Answer", r["answer"], "kg/h")],
            "tables": [], "charts": [], "warnings": []}

SECTION = Section("my_model", "My Model", "One-line description.", compute, report, INPUTS)
```

2. Register it in `public/bf_model/registry.py` (`SECTIONS` list — order = calculation order).
3. Add the file path to `public/bf_model/manifest.json` (a test checks you did).

The web page creates the input form and a results tab automatically.
Charts are plain [Plotly](https://plotly.com/javascript/) figure dicts, so any Plotly chart type works.
`report()` can also return `"equations"` (see `mass_balance.py`) to show a balance equation with numbers.

## Main assumptions

- Steady state; basis is hourly mass flows (t/h, Nm³/h). Hot-metal production follows from the Fe balance.
- Ores are given as dry analyses (Fe, FeO, gangue); the remainder to 100 % reports to slag as "other".
- Coke & coal by ultimate analysis; ash, dust and limestone compositions are fixed in `core/constants.py`.
- Hot-metal C, Si, Mn, P, S are targets; the rest of each element reports to slag. Sulphur to gas is neglected.
- All tuyere oxygen burns carbon to CO in the raceway; the remaining gasified carbon is solution loss / direct reduction (Rist approach).
- Heat losses are the closing term of the enthalpy balance; 60 % of them are distributed along the shaft wall in the thermal model.
- Reduction kinetics use temperature windows (semi-empirical) scaled to match r_d from the mass balance.

Results are engineering estimates for teaching and scoping, not plant guarantees.
