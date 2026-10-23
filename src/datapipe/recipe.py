"""Mapping and style files (SPEC §6): read them, check them against a look's schema (``look.toml``) and write them
in one canonical form, so a file the tuner saves round-trips (load, save, identical text).

Standard library only: Blender imports this file too (``sys.path`` has ``src``), and the tuner writes with it.

- A **mapping** (``mappings/<method>.toml``) says which of a run's sources drive the look's signals: ``ring``,
  ``[signals]``, ``[smooth]``, ``[hit]``, ``[motion]``.
- A **style** (``styles/<name>.toml``) is the look's shape and live values: ``[shape]`` rebuilds the geometry,
  ``[look]`` sets the sliders. A style may list only what it changes; the rest keep the schema's defaults.
"""

import tomllib
from pathlib import Path

INLINE_MAX = 3                 # a signal with more sources than this gets its own [signals.<name>] table
INT_KEYS = {("smooth", None), ("hit", "windup"), ("hit", "decay"), ("motion", "section_ease")}
MAPPING_KEYS = ("ring", "signals", "smooth", "hit", "motion")


def load(path: Path) -> dict:
    with open(path, "rb") as fh:
        return tomllib.load(fh)


def header(path: Path) -> str:
    """The comment block a file starts with (kept when the tuner saves over it)."""
    lines = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.startswith("#"):
            break
        lines.append(line)
    return "\n".join(lines)


def save(path: Path, text: str) -> bool:
    """Write ``text`` unless the file already holds it; returns whether it changed."""
    path = Path(path)
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return True


# ---- mappings ------------------------------------------------------------------------------------------------------

def dumps_mapping(cfg: dict, schema: dict, head: str = "") -> str:
    """A mapping in canonical form: ring, then the signals (short ones inline, in file order, then the long ones as
    tables), smooth, hit and motion, each line commented from the look's schema."""
    unknown = set(cfg) - set(MAPPING_KEYS)
    if unknown:
        raise ValueError(f"mapping: unknown keys {sorted(unknown)}; a mapping has {', '.join(MAPPING_KEYS)}")
    notes, drives = schema.get("recipe", {}), schema.get("signals", {})
    out = [head.rstrip() + "\n"] if head.strip() else []
    if "ring" in cfg:
        ring = cfg["ring"]
        out.append(_block([("ring", _inline({"track": ring["track"], "level": float(ring.get("level", 1.0))}),
                            notes.get("ring", ""))]))
    signals = cfg.get("signals", {})
    short = [(k, v) for k, v in signals.items() if len(v) <= INLINE_MAX]
    long_ = [(k, v) for k, v in signals.items() if len(v) > INLINE_MAX]
    if short or not long_:
        out.append(_table("signals", notes.get("signals", ""),
                          [(k, _inline({s: float(w) for s, w in v.items()}), drives.get(k, "")) for k, v in short]))
    for k, v in long_:
        out.append(_table(f"signals.{k}", drives.get(k, ""), [(_key(s), _value(float(w)), "") for s, w in v.items()]))
    if "smooth" in cfg:
        out.append(_table("smooth", notes.get("smooth", ""), [(k, _value(int(v)), "") for k, v in cfg["smooth"].items()]))
    if "hit" in cfg:
        rows = [(k, _inline({f: int(x) for f, x in v.items()}), "") for k, v in cfg["hit"].items()]
        out.append(_table("hit", notes.get("hit", ""), rows))
    if "motion" in cfg:
        rows = [(k, _value(int(v) if ("motion", k) in INT_KEYS else v if isinstance(v, str) else float(v)),
                 notes.get(k, "")) for k, v in cfg["motion"].items()]
        out.append(_table("motion", "", rows))
    return "\n".join(out)


# ---- styles --------------------------------------------------------------------------------------------------------

def check_style(style: dict, schema: dict) -> None:
    """Fail loud on a key the look doesn't have, a value of the wrong kind or outside its range."""
    unknown = set(style) - {"shape", "look"}
    if unknown:
        raise ValueError(f"style: unknown tables {sorted(unknown)}; a style has [shape] and [look]")
    for table in ("shape", "look"):
        known = schema[table]
        for key, value in style.get(table, {}).items():
            if key not in known:
                raise ValueError(f"style [{table}]: unknown key {key!r}; known: {', '.join(known)}")
            spec = known[key]
            if "options" in spec:
                if value not in spec["options"]:
                    raise ValueError(f"style [{table}] {key} = {value!r}: one of {', '.join(spec['options'])}")
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)) or (
                    isinstance(spec["default"], int) and not isinstance(value, int)):
                raise ValueError(f"style [{table}] {key} = {value!r}: a{'n integer' if isinstance(spec['default'], int) else ' number'}")
            if not spec["min"] <= value <= spec["max"]:
                raise ValueError(f"style [{table}] {key} = {value}: outside {spec['min']} .. {spec['max']}")


def resolve_style(style: dict, schema: dict) -> dict:
    """Every shape and look value: the style's, else the schema's default."""
    check_style(style, schema)
    return {table: {k: style.get(table, {}).get(k, spec["default"]) for k, spec in schema[table].items()}
            for table in ("shape", "look")}


def dumps_style(style: dict, schema: dict, head: str = "") -> str:
    """A style in canonical form: [shape], then [look], keys in the schema's order under their group's name."""
    check_style(style, schema)
    out = [head.rstrip() + "\n"] if head.strip() else []
    titles = {"shape": "rebuilds the tunnel's geometry", "look": "live: the sliders on NeonControls"}
    for table in ("shape", "look"):
        values = style.get(table, {})
        if not values:
            continue
        lines, group = [f"[{table}]  # {titles[table]}"], None
        rows = []
        for key, spec in schema[table].items():
            if key not in values:
                continue
            if spec["group"] != group:
                if rows:
                    lines.append(_rows(rows))
                    rows = []
                group = spec["group"]
                lines.append(f"# {group}")
            value = values[key]
            value = value if "options" in spec else int(value) if isinstance(spec["default"], int) else float(value)
            note = spec["label"] + (f" ({', '.join(spec['options'])})" if "options" in spec else "")
            rows.append((key, _value(value), note))
        lines.append(_rows(rows))
        out.append("\n".join(lines) + "\n")
    return "\n".join(out)


# ---- writing -------------------------------------------------------------------------------------------------------

def _table(name: str, note: str, rows: list) -> str:
    title = f"[{name}]" + (f"  # {note}" if note else "")
    return title + ("\n" + _rows(rows) if rows else "") + "\n"


def _block(rows: list) -> str:
    return _rows(rows) + "\n"


def _rows(rows: list) -> str:
    """``key = value  # note`` lines, keys padded to one width and notes to one column."""
    if not rows:
        return ""
    width = max(len(k) for k, _, _ in rows)
    body = [f"{k.ljust(width)} = {v}" for k, v, _ in rows]
    column = max(len(b) for b in body) + 2
    return "\n".join(b.ljust(column) + f"# {n}" if n else b for b, (_, _, n) in zip(body, rows))


def _inline(table: dict) -> str:
    return "{ " + ", ".join(f"{_key(k)} = {_value(v)}" for k, v in table.items()) + " }"


def _key(key: str) -> str:
    bare = key and all(ch.isascii() and (ch.isalnum() or ch in "_-") for ch in key)
    return key if bare else _string(key)


def _value(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        r = round(v, 4) + 0.0                  # + 0.0 turns -0.0 into 0.0
        return f"{r:.1f}" if r == int(r) and abs(r) < 1e15 else repr(r)
    if isinstance(v, str):
        return _string(v)
    raise TypeError(f"can't write {v!r} to TOML")


def _string(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
