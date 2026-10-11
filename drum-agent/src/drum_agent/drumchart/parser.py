"""Parser for the .drums chart text format (see references/format.md)."""
from __future__ import annotations

import re
import shlex
from fractions import Fraction as Fr
from math import gcd
from typing import Dict, List, Optional, Tuple

from .model import (INSTRUMENTS, REST_CHARS, STICKING_CHARS, STICKING_ROW, Bar, Chart,
                    Directive, Hit, Meter, Pattern, Section, lookup_instrument)

KNOWN_DIRECTIVES = {
    "dyn", "cresc", "dim", "text", "cue", "tempo", "time", "rit", "accel", "atempo",
    "fermata", "confidence", "break", "nosimile", "stop", "feel", "fill",
}
SECTION_KEYS = {"at", "mark", "confidence", "per-line", "note", "time", "tempo"}


class ChartError(Exception):
    def __init__(self, line: int, msg: str):
        super().__init__(f"line {line}: {msg}" if line else msg)
        self.line = line


def _strip_comment(s: str) -> str:
    out, q = [], None
    for i, ch in enumerate(s):
        if q:
            if ch == q:
                q = None
        elif ch in "\"'" and (i == 0 or s[i - 1] in " =\t@"):
            q = ch
        elif ch == "#" and (i == 0 or s[i - 1] in " \t"):
            break
        out.append(ch)
    return "".join(out).rstrip()


def _split_args(s: str, line: int) -> List[str]:
    try:
        return shlex.split(s)
    except ValueError as e:
        raise ChartError(line, f"could not parse arguments ({e}): {s}")


def _parse_directive(text: str, line: int) -> Directive:
    toks = _split_args(text, line)
    kind = toks[0].lstrip("@").lower()
    if kind == "decresc":
        kind = "dim"
    args, opts = [], {}
    for t in toks[1:]:
        if "=" in t and not t.startswith("\"") and re.match(r"^[a-z][a-z0-9_-]*=", t):
            k, v = t.split("=", 1)
            opts[k] = v
        else:
            args.append(t)
    return Directive(kind, args, opts, line)


def _split_directives(rest: str, line: int) -> Tuple[str, List[Directive]]:
    """Split 'x4 @dyn ff @text "Hi"' -> ('x4', [dyn, text])."""
    parts = re.split(r"\s(?=@[a-zA-Z])", " " + rest)
    head = parts[0].strip()
    dirs = [_parse_directive(p.strip(), line) for p in parts[1:] if p.strip()]
    return head, dirs


def _is_row(tokens: List[str]) -> bool:
    if len(tokens) < 2:
        return False
    code = tokens[0].upper()
    if code != STICKING_ROW and lookup_instrument(code) is None:
        return False
    body = " ".join(tokens[1:])
    return re.fullmatch(r"[\sA-Za-z\-\.\|\^]+", body) is not None


def _row_bars(body: str) -> List[List[str]]:
    segs = [s.strip() for s in body.split("|")]
    segs = [s for s in segs if s]
    return [s.split() for s in segs]


class Parser:
    def __init__(self, text: str):
        self.lines = text.splitlines()
        self.meta: Dict[str, str] = {}
        self.patterns: Dict[str, Pattern] = {}
        self.sections: List[Section] = []
        self.warnings: List[str] = []
        self.meter: Optional[Meter] = None
        self.pending: List[Directive] = []

    # -- helpers ---------------------------------------------------------
    def warn(self, line: int, msg: str):
        self.warnings.append(f"line {line}: {msg}")

    def _canon_inst(self, code: str, line: int) -> str:
        if code.upper() == STICKING_ROW:
            return STICKING_ROW
        inst = lookup_instrument(code)
        if inst is None:
            raise ChartError(line, f"unknown instrument {code!r}. Use one of: "
                             + ", ".join(INSTRUMENTS) + " (or ST for sticking)")
        return inst.code

    # -- main ------------------------------------------------------------
    def parse(self) -> Chart:
        i, n = 0, len(self.lines)
        in_header = True
        cur_pattern: Optional[Pattern] = None
        cur_section: Optional[Section] = None
        inline_rows: Optional[Tuple[int, List[Tuple[str, List[List[str]]]]]] = None

        def flush_inline():
            nonlocal inline_rows
            if inline_rows is None:
                return
            ln, rows = inline_rows
            inline_rows = None
            if not rows:
                raise ChartError(ln, "'bar' must be followed by instrument rows")
            pat = Pattern(f"_inline{ln}", ln, self._rows_to_bars(rows, ln))
            self._emit(cur_section, pat, 1, [], ln, inline=True)

        while i < n:
            ln = i + 1
            raw = _strip_comment(self.lines[i])
            i += 1
            if not raw.strip():
                continue
            s = raw.strip()
            toks = s.split()
            kw = toks[0].lower()

            # header lines
            if in_header and re.match(r"^[A-Za-z][A-Za-z0-9 _-]*:", s) and kw not in ("pattern", "section"):
                k, v = s.split(":", 1)
                self.meta[k.strip().lower()] = v.strip()
                continue
            if in_header and kw not in ("pattern", "section"):
                raise ChartError(ln, f"expected 'key: value' header, 'pattern' or 'section', got: {s}")
            if in_header:
                in_header = False
                self.meter = Meter.parse(self.meta.get("time", "4/4"))

            # rows (inside pattern or inline bar)
            if _is_row(toks):
                if inline_rows is not None:
                    inline_rows[1].append((self._canon_inst(toks[0], ln), _row_bars(" ".join(toks[1:]))))
                    continue
                if cur_pattern is not None:
                    self._add_pattern_row(cur_pattern, toks, ln)
                    continue
                raise ChartError(ln, "instrument row outside of a 'pattern' or 'bar' block")

            flush_inline()

            if kw == "pattern":
                cur_pattern = self._start_pattern(toks, ln)
                cur_section = None
                continue
            if kw == "section":
                if cur_pattern is not None:
                    self._finish_pattern(cur_pattern)
                cur_pattern = None
                name = s.split(None, 1)[1] if len(toks) > 1 else f"Section {len(self.sections) + 1}"
                if self.pending:
                    raise ChartError(ln, "directive(s) before 'section' were never applied to a bar")
                cur_section = Section(name=name.strip().strip('"'), line=ln)
                self.sections.append(cur_section)
                continue

            if cur_pattern is not None:
                raise ChartError(ln, f"unexpected line inside pattern {cur_pattern.name!r}: {s} "
                                 "(pattern bodies may only contain instrument rows)")
            if cur_section is None:
                raise ChartError(ln, f"line outside of any section: {s}")

            if kw.startswith("@"):
                d = _parse_directive(s, ln)
                self._check_directive(d)
                self.pending.append(d)
                continue
            if kw in ("time", "tempo"):
                d = _parse_directive("@" + s, ln)
                self.pending.append(d)
                continue
            if kw == "break":
                self.pending.append(Directive("break", [], {}, ln))
                continue
            if kw == "at":
                cur_section.at = toks[1] if len(toks) > 1 else ""
                continue
            if kw == "mark":
                cur_section.mark = toks[1] if len(toks) > 1 else ""
                continue
            if kw == "per-line":
                cur_section.per_line = int(toks[1])
                continue
            if kw == "confidence":
                a = _split_args(s, ln)[1:]
                if not a or a[0].lower() not in ("high", "medium", "low"):
                    raise ChartError(ln, "confidence must be high, medium or low")
                cur_section.confidence = a[0].lower()
                cur_section.confidence_note = " ".join(a[1:])
                continue
            if kw == "note":
                cur_section.notes.append(" ".join(_split_args(s, ln)[1:]))
                continue
            if kw == "play":
                head, dirs = _split_directives(s.split(None, 1)[1] if len(toks) > 1 else "", ln)
                for d in dirs:
                    self._check_directive(d)
                hp = head.split()
                if not hp:
                    raise ChartError(ln, "play needs a pattern name")
                name = hp[0]
                times = 1
                if len(hp) > 1:
                    m = re.fullmatch(r"[x×*]?(\d+)[x×]?", hp[1])
                    if not m:
                        raise ChartError(ln, f"bad repeat count {hp[1]!r} (use e.g. x4)")
                    times = int(m.group(1))
                if name not in self.patterns:
                    raise ChartError(ln, f"unknown pattern {name!r}. Defined: {', '.join(self.patterns) or '(none)'}")
                self._emit(cur_section, self.patterns[name], times, dirs, ln)
                continue
            if kw == "rest":
                head, dirs = _split_directives(s.split(None, 1)[1] if len(toks) > 1 else "1", ln)
                a = _split_args(head, ln)
                nb = int(a[0]) if a and a[0].isdigit() else 1
                each = any(x.lower() == "each" for x in a[1:])
                text = " ".join(x for x in a[1:] if x.lower() != "each")
                self._emit_rest(cur_section, nb, text, each, dirs, ln)
                continue
            if kw == "bar":
                inline_rows = (ln, [])
                rest = s.split(None, 1)[1] if len(toks) > 1 else ""
                if rest.strip():
                    _, dirs = _split_directives(rest, ln)
                    for d in dirs:
                        self._check_directive(d)
                    self.pending.extend(dirs)
                continue
            raise ChartError(ln, f"unknown statement {toks[0]!r}. Expected play, rest, bar, @directive, "
                             "at, mark, confidence, note, per-line, time, tempo, break")

        flush_inline()
        if cur_pattern is not None:
            self._finish_pattern(cur_pattern)
        if in_header:
            raise ChartError(0, "chart has no sections")
        if self.pending:
            self.warn(self.pending[0].line, "directive(s) at the end of the chart were never applied to a bar")
        chart = Chart(self.meta, self.patterns, self.sections, self.warnings)
        _finalize(chart)
        return chart

    # -- patterns --------------------------------------------------------
    def _start_pattern(self, toks: List[str], ln: int) -> Pattern:
        if len(toks) < 2:
            raise ChartError(ln, "pattern needs a name")
        name = toks[1]
        if name in self.patterns:
            raise ChartError(ln, f"pattern {name!r} already defined (line {self.patterns[name].line})")
        meter = None
        base = None
        j = 2
        while j < len(toks):
            if toks[j].lower() == "from" and j + 1 < len(toks):
                base = toks[j + 1]
                j += 2
            elif toks[j].lower() == "time" and j + 1 < len(toks):
                spec = toks[j + 1]
                if j + 2 < len(toks) and re.fullmatch(r"\d+(\+\d+)+", toks[j + 2]):
                    spec += " " + toks[j + 2]
                    j += 1
                meter = Meter.parse(spec)
                j += 2
            else:
                raise ChartError(ln, f"unexpected {toks[j]!r} in pattern header (use: pattern NAME [from BASE] [time 6/8])")
        p = Pattern(name, ln, [], meter)
        if base:
            if base not in self.patterns:
                raise ChartError(ln, f"base pattern {base!r} is not defined (yet)")
            b = self.patterns[base]
            p.bars = [{k: list(v) for k, v in bar.items()} for bar in b.bars]
            p.meter = p.meter or b.meter
            p._from = base  # type: ignore[attr-defined]
            p._overrides = set()  # type: ignore[attr-defined]
        self.patterns[name] = p
        return p

    def _add_pattern_row(self, p: Pattern, toks: List[str], ln: int):
        inst = self._canon_inst(toks[0], ln)
        bars = _row_bars(" ".join(toks[1:]))
        if hasattr(p, "_from"):
            if inst in p._overrides:  # type: ignore[attr-defined]
                raise ChartError(ln, f"{inst} given twice in pattern {p.name!r}")
            p._overrides.add(inst)  # type: ignore[attr-defined]
            if len(bars) != len(p.bars):
                raise ChartError(ln, f"pattern {p.name!r} is based on a {len(p.bars)}-bar pattern but this row has {len(bars)} bar(s)")
            for bi, toks_ in enumerate(bars):
                p.bars[bi][inst] = toks_
            return
        if not p.bars:
            p.bars = [dict() for _ in bars]
        if len(bars) != len(p.bars):
            raise ChartError(ln, f"row has {len(bars)} bar(s) but earlier rows of pattern {p.name!r} have {len(p.bars)}")
        for bi, toks_ in enumerate(bars):
            if inst in p.bars[bi]:
                raise ChartError(ln, f"{inst} given twice in pattern {p.name!r}")
            p.bars[bi][inst] = toks_

    def _finish_pattern(self, p: Pattern):
        if not p.bars:
            raise ChartError(p.line, f"pattern {p.name!r} has no rows")

    def _rows_to_bars(self, rows, ln) -> List[Dict[str, List[str]]]:
        nb = len(rows[0][1])
        bars = [dict() for _ in range(nb)]
        for inst, b in rows:
            if len(b) != nb:
                raise ChartError(ln, "all rows of a 'bar' block must have the same number of bars")
            for bi, t in enumerate(b):
                if inst in bars[bi]:
                    raise ChartError(ln, f"{inst} given twice in bar block")
                bars[bi][inst] = t
        return bars

    # -- emitting bars ---------------------------------------------------
    def _check_directive(self, d: Directive):
        if d.kind not in KNOWN_DIRECTIVES:
            raise ChartError(d.line, f"unknown directive @{d.kind}. Known: " + ", ".join(sorted("@" + k for k in KNOWN_DIRECTIVES)))

    def _take_pending(self, extra: List[Directive]) -> List[Directive]:
        ds = self.pending + extra
        self.pending = []
        for d in ds:
            if d.kind == "time":
                if not d.args:
                    raise ChartError(d.line, "@time needs a time signature, e.g. @time 3/4")
                self.meter = Meter.parse(" ".join(d.args))
        return ds

    def _normalize_bar(self, raw: Dict[str, List[str]], meter: Meter, ln: int, pname: str) -> Dict[str, List[str]]:
        ng = len(meter.groups)
        out: Dict[str, List[str]] = {}
        for inst, toks in raw.items():
            toks = list(toks)
            if len(toks) != ng:
                if len(toks) == 1 and len(toks[0]) % ng == 0 and len(set(meter.groups)) == 1:
                    k = len(toks[0]) // ng
                    toks = [toks[0][j * k:(j + 1) * k] for j in range(ng)]
                else:
                    raise ChartError(ln, f"{pname}: {inst} row has {len(toks)} beat group(s) but {meter} needs {ng} "
                                     f"(separate beats with spaces, e.g. 'x-x- x-x- x-x- x-x-')")
            allowed = STICKING_CHARS if inst == STICKING_ROW else INSTRUMENTS[inst].chars
            for g, t in enumerate(toks):
                for ch in t:
                    if ch in REST_CHARS:
                        continue
                    if ch not in allowed:
                        name = "sticking" if inst == STICKING_ROW else INSTRUMENTS[inst].name
                        raise ChartError(ln, f"{pname}: '{ch}' is not valid for {name} ({inst}); allowed: {allowed} and - for silence")
            out[inst] = toks
        if not out:
            raise ChartError(ln, f"{pname}: bar has no rows")
        # make every group the same length across rows (expand coarser rows)
        for g in range(ng):
            lens = {len(v[g]) for v in out.values()}
            L = max(lens)
            for l in lens:
                if L % l != 0:
                    raise ChartError(ln, f"{pname}: beat {g + 1} mixes incompatible subdivisions ({sorted(lens)}); "
                                     "write all rows of that beat with the same number of characters")
            for inst in out:
                t = out[inst][g]
                if len(t) != L:
                    k = L // len(t)
                    out[inst][g] = "".join(c + "-" * (k - 1) for c in t)
        return out

    def _emit(self, sec: Section, pat: Pattern, times: int, dirs: List[Directive], ln: int, inline: bool = False):
        for t in range(times):
            for bi, raw in enumerate(pat.bars):
                ds = self._take_pending(dirs if (t == 0 and bi == 0) else [])
                meter = self.meter
                if pat.meter is not None and pat.meter != meter:
                    if t == 0 and bi == 0 and not any(d.kind == "time" for d in ds):
                        raise ChartError(ln, f"pattern {pat.name!r} is in {pat.meter} but the current time is {meter}; "
                                         f"add '@time {pat.meter.label}' before it")
                pname = "bar" if inline else f"pattern {pat.name!r}"
                rows = self._normalize_bar(raw, meter, pat.line if not inline else ln, pname)
                bar = Bar(meter=meter, rows=rows, pattern=None if inline else f"{pat.name}#{bi}",
                          directives=ds, line=ln, section=sec)
                sec.bars.append(bar)

    def _emit_rest(self, sec: Section, nb: int, text: str, each: bool, dirs: List[Directive], ln: int):
        if nb < 1:
            raise ChartError(ln, "rest needs a positive number of bars")
        if each or nb == 1:
            for k in range(nb):
                ds = self._take_pending(dirs if k == 0 else [])
                m = self.meter
                bar = Bar(meter=m, rows={"SN": ["-" * 1 for _ in m.groups]}, pattern="_rest", directives=ds,
                          line=ln, section=sec, rest_text=text if k == 0 else "")
                sec.bars.append(bar)
        else:
            ds = self._take_pending(dirs)
            m = self.meter
            bar = Bar(meter=m, rows={"SN": ["-" for _ in m.groups]}, pattern="_mrest", directives=ds,
                      line=ln, section=sec, rest_bars=nb, rest_text=text)
            sec.bars.append(bar)


def _parse_tempo(spec: str, line: int = 0) -> Tuple[float, str]:
    """'117' -> (117, 'q'); '60 q.' -> (90 quarter-equivalent, 'q.'); returns quarter-note bpm and unit."""
    a = spec.split()
    try:
        bpm = float(a[0])
    except (ValueError, IndexError):
        raise ChartError(line, f"bad tempo {spec!r}")
    unit = a[1] if len(a) > 1 and a[1] in ("q", "q.", "h", "h.", "e", "e.") else "q"
    factor = {"q": 1, "q.": 1.5, "h": 2, "h.": 3, "e": 0.5, "e.": 0.75}[unit]
    return bpm * factor, unit


def _finalize(chart: Chart):
    tempo_q, _ = _parse_tempo(chart.meta.get("tempo", "120"))
    t = 0.0
    num = 1
    for sec in chart.sections:
        if not sec.bars:
            raise ChartError(sec.line, f"section {sec.name!r} has no bars")
        for bar in sec.bars:
            for d in bar.get_directives("tempo"):
                if d.args:
                    tempo_q, _ = _parse_tempo(" ".join(d.args), d.line)
            for d in bar.get_directives("confidence"):
                bar.confidence = (d.args[0].lower() if d.args else "low")
                bar.confidence_note = " ".join(d.args[1:])
            bar.number = num
            bar.tempo = tempo_q
            bar.start_time = t
            nb = bar.rest_bars or 1
            t += nb * float(bar.meter.length) * 4 * 60.0 / tempo_q
            num += nb
            # hits
            bar.hits = []
            for inst, groups in bar.rows.items():
                off = Fr(0)
                for g, s in enumerate(groups):
                    n = len(s)
                    for k, ch in enumerate(s):
                        if ch not in REST_CHARS:
                            bar.hits.append(Hit(inst, g, k, n, ch, off + bar.meter.groups[g] * Fr(k, n)))
                    off += bar.meter.groups[g]
    chart.meta["_total_seconds"] = f"{t:.1f}"
    chart.meta["_total_bars"] = str(num - 1)


def parse_chart(text: str) -> Chart:
    return Parser(text).parse()
