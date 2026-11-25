"""Declarative building blocks shared by every model section.

A *section* declares its input fields and two functions:

    compute(inp, ctx) -> dict   raw numbers, stored in ctx[section.id] for later sections
    report(inp, ctx)  -> dict   what the web page shows (kpis, tables, charts, warnings)

The web front-end builds its forms and tabs automatically from this metadata,
so adding a new model never requires touching HTML or JavaScript.
"""

from dataclasses import dataclass, field, asdict
from typing import Callable, List, Optional


@dataclass
class Field:
    key: str                 # unique across ALL sections
    label: str
    unit: str = ""
    default: float = 0.0
    min: Optional[float] = None
    max: Optional[float] = None
    step: Optional[float] = None
    help: str = ""


@dataclass
class Group:
    id: str
    title: str
    fields: List[Field]
    description: str = ""
    collapsed: bool = False


@dataclass
class Section:
    id: str
    title: str
    description: str
    compute: Callable
    report: Callable
    inputs: List[Group] = field(default_factory=list)
    icon: str = "chart"

    def meta(self):
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "icon": self.icon,
            "inputs": [asdict(g) for g in self.inputs],
        }


# ------------------------------------------------------------ result helpers
def kpi(label, value, unit="", digits=1, hint="", status=None):
    """A headline number. status: None | 'ok' | 'warn' | 'bad'."""
    return {"label": label, "value": round(value, digits) if isinstance(value, float) else value,
            "unit": unit, "hint": hint, "status": status}


def table(title, columns, rows, digits=2, note=""):
    def fmt(v):
        return round(v, digits) if isinstance(v, float) else v
    return {"title": title, "columns": columns, "rows": [[fmt(c) for c in r] for r in rows], "note": note}


def chart(chart_id, title, data, layout=None, note=""):
    """A Plotly figure specification (rendered as-is by the front-end)."""
    return {"id": chart_id, "title": title, "data": data, "layout": layout or {}, "note": note}


def in_range(value, lo, hi):
    return "ok" if lo <= value <= hi else "warn"
