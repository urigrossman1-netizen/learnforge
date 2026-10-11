"""Data model for drum charts: meters, instruments, bars, sections."""
from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction as Fr
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# Instruments
# ---------------------------------------------------------------------------
# pos = staff position in half-spaces above the bottom line (E4 = 0, F4 = 1,
# G4 = 2, A4 = 3, B4 = 4, C5 = 5, D5 = 6, E5 = 7, F5 = 8, G5 = 9, A5 = 10,
# B5 = 11, C6 = 12, D4 = -1).  voice "up" = hands (stems up), "down" = feet.
# head = default SMuFL notehead.  chars = articulation letters allowed in the
# grid for that instrument (see FORMAT in references/format.md).


@dataclass(frozen=True)
class Instrument:
    code: str
    name: str
    short: str          # label used in the count grid
    pos: int
    voice: str          # "up" | "down"
    head: str
    family: str         # colour family for the grid
    chars: str
    order: int          # top-to-bottom order in grids/legends


_COMMON = "xXgfFdz"
_CYM = "xXk"
# Positions/noteheads follow Weinberg's PAS "Guide to Standardized Drumset Notation"
# (see references/notation-key.md for sources and the disagreements we resolved).
INSTRUMENTS: Dict[str, Instrument] = {i.code: i for i in [
    Instrument("TB", "Tambourine", "Tamb", 13, "up", "noteheadSquareBlack", "perc", "xXg", 0),
    Instrument("SP", "Splash", "Splash", 12, "up", "noteheadXBlack", "crash", _CYM, 1),
    Instrument("CH", "China", "China", 11, "up", "noteheadHeavyXHat", "crash", _CYM, 2),
    Instrument("C2", "Crash 2", "Crash 2", 11, "up", "noteheadXBlack", "crash", _CYM, 3),
    Instrument("CR", "Crash", "Crash", 10, "up", "noteheadXBlack", "crash", _CYM, 4),
    Instrument("HH", "Hi-hat", "Hi-hat", 9, "up", "noteheadXBlack", "hat", "xXoOhgfdz", 5),
    Instrument("RD", "Ride", "Ride", 8, "up", "noteheadXBlack", "ride", "xXbBgk", 6),
    Instrument("R2", "Ride 2", "Ride 2", 6, "up", "noteheadXBlack", "ride", "xXbBgk", 7),
    Instrument("CB", "Cowbell", "Cowbell", 7, "up", "noteheadTriangleDownBlack", "perc", "xXg", 8),
    Instrument("T1", "High tom", "High tom", 7, "up", "noteheadBlack", "tom", _COMMON, 9),
    Instrument("T2", "Mid tom", "Mid tom", 6, "up", "noteheadBlack", "tom", _COMMON, 10),
    Instrument("SN", "Snare", "Snare", 5, "up", "noteheadBlack", "snare", _COMMON + "rRc", 11),
    Instrument("T3", "Low tom", "Low tom", 4, "up", "noteheadBlack", "tom", _COMMON, 12),
    Instrument("FT", "Floor tom", "Floor tom", 3, "up", "noteheadBlack", "tom", _COMMON, 13),
    Instrument("F2", "Floor tom 2", "Floor 2", 2, "up", "noteheadBlack", "tom", _COMMON, 14),
    Instrument("BD", "Bass drum", "Kick", 1, "down", "noteheadBlack", "kick", "xXg", 15),
    Instrument("B2", "Bass drum 2", "Kick 2", 0, "down", "noteheadBlack", "kick", "xXg", 16),
    Instrument("HF", "Hi-hat foot", "HH foot", -1, "down", "noteheadXBlack", "foot", "xXo", 17),
]}

ALIASES = {
    "C1": "CR", "CC": "CR", "CRASH": "CR", "CRASH2": "C2", "CHINA": "CH", "SPL": "SP",
    "SPLASH": "SP", "RIDE": "RD", "RC": "RD", "R": "RD", "RIDE2": "R2", "RD2": "R2", "HHC": "HH", "HAT": "HH",
    "HP": "HF", "HHF": "HF", "HHP": "HF", "PEDAL": "HF", "SD": "SN", "S": "SN", "SNARE": "SN",
    "HT": "T1", "MT": "T2", "LT": "FT", "FLOOR": "FT", "FT1": "FT", "FT2": "F2", "T4": "F2",
    "KD": "BD", "K": "BD", "B": "BD", "KICK": "BD", "BASS": "BD", "BD2": "B2", "KD2": "B2", "K2": "B2",
    "COW": "CB", "TAMB": "TB",
}

STICKING_ROW = "ST"
STICKING_CHARS = "RLB"
REST_CHARS = "-."


def lookup_instrument(code: str) -> Optional[Instrument]:
    c = code.upper()
    c = ALIASES.get(c, c)
    return INSTRUMENTS.get(c)


# ---------------------------------------------------------------------------
# Meter
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Meter:
    num: int
    den: int
    groups: tuple  # each group's duration as a Fraction of a whole note

    @staticmethod
    def parse(text: str) -> "Meter":
        """'4/4', '6/8', '7/8 2+2+3', '12/8', '2/2', '5/4 3+2' (groups in beats of den)."""
        parts = text.replace("(", " ").replace(")", " ").split()
        if not parts or "/" not in parts[0]:
            raise ValueError(f"bad time signature {text!r} (expected e.g. 4/4, 6/8, 7/8 2+2+3)")
        num, den = parts[0].split("/")
        num, den = int(num), int(den)
        if den not in (2, 4, 8, 16) or num < 1 or num > 32:
            raise ValueError(f"unsupported time signature {num}/{den}")
        unit = Fr(1, den)
        if len(parts) > 1:
            g = [int(x) for x in parts[1].split("+")]
            if sum(g) != num:
                raise ValueError(f"grouping {parts[1]} does not add up to {num}")
            groups = tuple(unit * x for x in g)
        elif den == 8 and num % 3 == 0 and num > 3:
            groups = tuple(Fr(3, 8) for _ in range(num // 3))       # compound: 6/8 9/8 12/8
        elif den == 8 and num > 3:
            # odd eighths meters default to 2+2+...+3
            n2 = (num - 3) // 2
            g = [2] * n2 + [3]
            if sum(g) != num:
                g = [2] * (num // 2)
            groups = tuple(unit * x for x in g)
        elif den == 16 and num % 3 == 0 and num > 3:
            groups = tuple(Fr(3, 16) for _ in range(num // 3))
        else:
            groups = tuple(unit for _ in range(num))
        return Meter(num, den, groups)

    @property
    def length(self) -> Fr:
        return Fr(self.num, self.den)

    @property
    def label(self) -> str:
        return f"{self.num}/{self.den}"

    @property
    def compound(self) -> bool:
        return all(g == Fr(3, self.den) for g in self.groups) and self.den >= 8

    def __str__(self):
        return self.label


# ---------------------------------------------------------------------------
# Chart structure
# ---------------------------------------------------------------------------
@dataclass
class Hit:
    inst: str            # instrument code (or "ST" for sticking)
    group: int
    slot: int
    nslots: int          # slots in this group
    art: str             # articulation char from the grid
    onset: Fr            # from start of bar, fraction of whole note


@dataclass
class Directive:
    kind: str
    args: List[str]
    opts: Dict[str, str]
    line: int


@dataclass
class Bar:
    meter: Meter
    rows: Dict[str, List[str]]          # inst code -> list of group strings
    pattern: Optional[str] = None       # name of the pattern it came from (or None)
    directives: List[Directive] = field(default_factory=list)
    line: int = 0
    rest_bars: int = 0                  # >0 -> multi-bar rest placeholder of N bars
    rest_text: str = ""
    # filled in later
    number: int = 0                     # 1-based bar number in the song
    section: Optional["Section"] = None
    simile: int = 0                     # 0 = written out, 1 = one-bar repeat, 2 = two-bar repeat (first half), 3 = second half
    simile_count: int = 0               # position in a run of identical bars (for counting numbers)
    tempo: float = 0.0
    start_time: float = 0.0             # seconds from song start
    hits: List[Hit] = field(default_factory=list)
    confidence: str = ""
    confidence_note: str = ""

    def nslots(self, g: int) -> int:
        for r in self.rows.values():
            return len(r[g])
        return 1

    def group_sizes(self) -> List[int]:
        for r in self.rows.values():
            return [len(x) for x in r]
        return [1] * len(self.meter.groups)

    def signature(self) -> tuple:
        """Content identity used for simile detection (ignores directives)."""
        if self.rest_bars:
            return ("rest", self.rest_bars)
        return (self.meter.label, tuple(sorted((k, tuple(v)) for k, v in self.rows.items()
                                               if any(c not in REST_CHARS for c in "".join(v)))))

    def has_directive(self, kind: str) -> bool:
        return any(d.kind == kind for d in self.directives)

    def get_directives(self, kind: str) -> List[Directive]:
        return [d for d in self.directives if d.kind == kind]

    @property
    def is_empty(self) -> bool:
        return not any(c not in REST_CHARS for k, v in self.rows.items() if k != STICKING_ROW for c in "".join(v))


@dataclass
class Section:
    name: str
    line: int
    mark: str = ""
    at: str = ""                 # timestamp in the recording, e.g. "0:25"
    confidence: str = ""
    confidence_note: str = ""
    per_line: int = 0
    notes: List[str] = field(default_factory=list)
    bars: List[Bar] = field(default_factory=list)


@dataclass
class Pattern:
    name: str
    line: int
    bars: List[Dict[str, List[str]]]    # per bar: inst -> group strings (raw tokens)
    meter: Optional[Meter] = None


@dataclass
class Chart:
    meta: Dict[str, str]
    patterns: Dict[str, Pattern]
    sections: List[Section]
    warnings: List[str] = field(default_factory=list)

    @property
    def bars(self) -> List[Bar]:
        return [b for s in self.sections for b in s.bars]
