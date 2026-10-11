"""Precise chart edits, version history and change lists for .drums files.

- `show_bar` / `set_bar`: look at or replace exactly one bar. A bar that comes
  from `play pattern xN` is split out of the run as an inline `bar` block, so the
  edit never leaks into other bars that share the pattern.
- `snapshot` / `versions` / `restore`: every edit and render keeps the previous
  text in `.history/<chart name>/` next to the chart, so any earlier version
  (and undo) is one command away.
- `diff`: what changed between two charts bar by bar (e.g. the machine draft
  and the final chart), so every correction is visible.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import time
from fractions import Fraction as Fr
from pathlib import Path

from .model import INSTRUMENTS, STICKING_ROW, Bar, Chart
from .parser import parse_chart

# ---------------------------------------------------------------------------
# one bar


def find_bar(chart: Chart, number: int) -> Bar:
    for b in chart.bars:
        if b.number == number or (b.rest_bars and b.number <= number < b.number + b.rest_bars):
            return b
    raise ValueError(f"bar {number} does not exist (the chart has {chart.meta.get('_total_bars')} bars)")


def bar_text(bar: Bar) -> str:
    """The bar's rows in .drums syntax (patterns and `from` already resolved)."""
    if bar.rest_bars:
        return "(rest)"
    order = sorted((c for c in bar.rows), key=lambda c: INSTRUMENTS[c].order if c in INSTRUMENTS else 99)
    return "\n".join(f"{c:<3} {' '.join(bar.rows[c])}" for c in order)


def show_bar(text: str, number: int) -> str:
    chart = parse_chart(text)
    bar = find_bar(chart, number)
    sec = bar.section
    idx = sec.bars.index(bar) + 1 if sec else 0
    head = [f"bar {bar.number}: {sec.name if sec else '?'} bar {idx}, time {bar.meter.num}/{bar.meter.den}, "
            f"tempo {bar.tempo:g}, from {'pattern ' + bar.pattern.split('#')[0] if bar.pattern else 'an inline bar'}"]
    for d in bar.directives:
        head.append("@" + " ".join([d.kind] + d.args))
    return "\n".join(head + [bar_text(bar)])


def set_bar(text: str, number: int, rows: str) -> str:
    """Replace bar `number` with `rows` ('HH x-x- ...' lines, or ';'-separated).

    Instruments you leave out are removed from that bar. Directives on the bar
    (fill, confidence, dynamics...) are kept.
    """
    chart = parse_chart(text)
    bar = find_bar(chart, number)
    if bar.rest_bars:
        raise ValueError(f"bar {number} is inside a multi-bar rest; rewrite that `rest` line instead")
    new_rows = [r.strip() for r in re.split(r"[;\n]", rows) if r.strip()]
    for r in new_rows:
        code = r.split()[0]
        if code.upper() != STICKING_ROW and code.upper() not in INSTRUMENTS:
            from .model import lookup_instrument

            if lookup_instrument(code) is None:
                raise ValueError(f"unknown instrument {code!r} in {r!r}")
    lines = text.split("\n")
    li = bar.line - 1
    stmt = lines[li]
    indent = re.match(r"\s*", stmt).group(0)
    same = [b for b in chart.bars if b.line == bar.line and not b.rest_bars]
    k = same.index(bar)
    m = re.match(r"\s*play\s+(\S+)(?:\s+x(\d+))?(.*)$", stmt)
    block = [f"{indent}bar"] + [f"{indent}  {r}" for r in new_rows]
    if m:
        name, count, rest = m.group(1), int(m.group(2) or 1), m.group(3).strip()
        before, after = k, count - k - 1
        out = []
        own_dirs = rest if k == 0 else ""
        if before:
            out.append(f"{indent}play {name}" + (f" x{before}" if before > 1 else "") + (f" {rest}" if rest else ""))
        if own_dirs:
            out += [f"{indent}{d}" for d in _split_directives(own_dirs)]
        out += block
        if after:
            out.append(f"{indent}play {name}" + (f" x{after}" if after > 1 else ""))
        lines[li : li + 1] = out
    elif re.match(r"\s*bar\b", stmt):
        end = li + 1
        while end < len(lines) and lines[end].strip() and len(re.match(r"\s*", lines[end]).group(0)) > len(indent) \
                and not lines[end].strip().startswith("@"):
            end += 1
        lines[li:end] = block
    else:
        raise ValueError(f"line {bar.line} ({stmt.strip()!r}) is not a play or bar statement")
    new_text = "\n".join(lines)
    parse_chart(new_text)  # must still be a valid chart
    return new_text


def _split_directives(text: str) -> list[str]:
    """'@fill @confidence medium "a b"' -> ['@fill', '@confidence medium "a b"']."""
    return [p.strip() for p in re.split(r"\s(?=@)", " " + text) if p.strip()]


# ---------------------------------------------------------------------------
# versions


def _history_dir(path: Path) -> Path:
    return path.parent / ".history" / path.name


def snapshot(path: str | Path, text: str | None = None) -> Path | None:
    """Keep a copy of the chart's current text (skipped when it equals the last copy)."""
    path = Path(path)
    if text is None:
        if not path.exists():
            return None
        text = path.read_text(encoding="utf-8")
    digest = hashlib.sha1(text.encode()).hexdigest()[:8]
    hist = _history_dir(path)
    existing = sorted(hist.glob("*.drums")) if hist.exists() else []
    if existing and existing[-1].stem.endswith(digest):
        return existing[-1]
    hist.mkdir(parents=True, exist_ok=True)
    dest = hist / f"{time.strftime('%Y%m%d-%H%M%S')}-{len(existing) + 1:03d}-{digest}.drums"
    dest.write_text(text, encoding="utf-8")
    return dest


def versions(path: str | Path) -> list[Path]:
    hist = _history_dir(Path(path))
    return sorted(hist.glob("*.drums")) if hist.exists() else []


def _position(path: Path, text: str) -> int | None:
    """Index (0-based) of the newest saved version identical to `text`."""
    digest = hashlib.sha1(text.encode()).hexdigest()[:8]
    vs = versions(path)
    hits = [i for i, v in enumerate(vs) if v.stem.endswith(digest)]
    return hits[-1] if hits else None


def undo(path: str | Path) -> Path:
    """Step back to the version before the current text (saving the current text first)."""
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    i = _position(path, text)
    if i is None:
        snapshot(path, text)
        i = len(versions(path)) - 1
    if i < 1:
        raise ValueError("nothing to undo: this is the oldest saved version")
    chosen = versions(path)[i - 1]
    shutil.copyfile(chosen, path)
    return chosen


def redo(path: str | Path) -> Path:
    """Step forward again after an undo."""
    path = Path(path)
    i = _position(path, path.read_text(encoding="utf-8"))
    vs = versions(path)
    if i is None or i + 1 >= len(vs):
        raise ValueError("nothing to redo")
    shutil.copyfile(vs[i + 1], path)
    return vs[i + 1]


def restore(path: str | Path, version: int) -> Path:
    """Put version N (1 = oldest; negative counts back from the newest) back in place;
    the current text is kept as a new version first, so a restore can be undone too."""
    path = Path(path)
    vs = versions(path)
    if not vs:
        raise ValueError(f"{path} has no saved versions yet")
    try:
        chosen = vs[version - 1] if version > 0 else vs[version]
    except IndexError:
        raise ValueError(f"version {version} does not exist ({len(vs)} saved)") from None
    snapshot(path)
    shutil.copyfile(chosen, path)
    return chosen


# ---------------------------------------------------------------------------
# changes


def _hits(bar: Bar) -> dict[tuple, str]:
    return {(h.inst, h.onset): h.art for h in bar.hits if h.inst != STICKING_ROW}


def _where(bar: Bar, onset: Fr) -> str:
    """'2&' style position of an onset within its bar."""
    pos, acc = onset, Fr(0)
    for g, d in enumerate(bar.meter.groups):
        if pos < acc + d:
            frac = (pos - acc) / d
            names = {Fr(0): "", Fr(1, 4): "e", Fr(1, 2): "&", Fr(3, 4): "a", Fr(1, 3): "trip", Fr(2, 3): "let"}
            return f"{g + 1}{names.get(frac, f'+{frac}')}"
        acc += d
    return str(onset)


def diff(old_text: str, new_text: str) -> list[str]:
    """Human-readable list of changes from old to new, bar by bar."""
    a, b = parse_chart(old_text), parse_chart(new_text)
    out = []
    for key in ("title", "tempo", "time", "source-kind", "notation"):
        if a.meta.get(key) != b.meta.get(key):
            out.append(f"{key}: {a.meta.get(key)!r} -> {b.meta.get(key)!r}")
    an = [(s.name, s.bars[0].number) for s in a.sections]
    bn = [(s.name, s.bars[0].number) for s in b.sections]
    if an != bn:
        out.append("sections: " + ", ".join(f"{n} @{i}" for n, i in an) + "  ->  "
                   + ", ".join(f"{n} @{i}" for n, i in bn))
    na, nb = a.meta.get("_total_bars"), b.meta.get("_total_bars")
    if na != nb:
        out.append(f"bars: {na} -> {nb} (compared bar by bar from bar 1)")
    for ba, bb in zip(a.bars, b.bars):
        changes = []
        if (ba.meter.num, ba.meter.den) != (bb.meter.num, bb.meter.den):
            changes.append(f"time {ba.meter.num}/{ba.meter.den} -> {bb.meter.num}/{bb.meter.den}")
        if round(ba.tempo, 2) != round(bb.tempo, 2):
            changes.append(f"tempo {ba.tempo:g} -> {bb.tempo:g}")
        ha, hb = _hits(ba), _hits(bb)
        for inst in sorted({k[0] for k in ha} | {k[0] for k in hb}):
            added = [f"{_where(bb, o)}{'' if hb[(i, o)] == 'x' else '(' + hb[(i, o)] + ')'}"
                     for (i, o) in sorted(hb) if i == inst and (i, o) not in ha]
            removed = [_where(ba, o) for (i, o) in sorted(ha) if i == inst and (i, o) not in hb]
            changed = [f"{_where(bb, o)} {ha[(i, o)]}->{hb[(i, o)]}" for (i, o) in sorted(hb)
                       if i == inst and (i, o) in ha and ha[(i, o)] != hb[(i, o)]]
            parts = ([f"+{' +'.join(added)}"] if added else []) + ([f"-{' -'.join(removed)}"] if removed else []) \
                + changed
            if parts:
                changes.append(f"{inst} {' '.join(parts)}")
        conf = (ba.confidence, bb.confidence)
        if conf[0] != conf[1]:
            changes.append(f"confidence {conf[0] or 'none'} -> {conf[1] or 'none'}")
        if changes:
            out.append(f"bar {bb.number}: " + "; ".join(changes))
    return out
