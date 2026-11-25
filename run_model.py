"""Run the blast furnace model from the command line (no browser needed).

    python run_model.py                      # default case, prints KPIs
    python run_model.py inputs.json          # custom inputs (exported from the web page)
    python run_model.py inputs.json out.json # also write full results
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "public"))

from bf_model import registry  # noqa: E402


def main():
    inputs = json.loads(Path(sys.argv[1]).read_text()) if len(sys.argv) > 1 else {}
    t0 = time.perf_counter()
    out = registry.run(inputs)
    dt = time.perf_counter() - t0
    for sid, res in out["results"].items():
        print(f"\n=== {sid} ===")
        if res.get("error"):
            print("ERROR:", res["trace"])
        for k in res["kpis"]:
            print(f"  {k['label']:<38} {k['value']!s:>12} {k['unit']:<12} {k.get('hint') or ''}")
        for w in res["warnings"]:
            print("  WARNING:", w)
    print(f"\nRun time: {dt * 1000:.0f} ms")
    if len(sys.argv) > 2:
        Path(sys.argv[2]).write_text(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
