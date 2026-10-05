#!/usr/bin/env python3
"""BlueBook Buddy -- finalize a messy pile of legal research into Bluebook-formatted,
appellate-brief citations.

Design principles
-----------------
* Deterministic and offline. No network, no third-party packages.
* Never invents facts. It normalizes what you typed (spacing, reporter
  abbreviations, circuit ordinals, pinpoint ranges, case-name abbreviations)
  and FLAGS everything it cannot verify (missing court, missing year,
  missing pinpoint, WL/Lexis cites, supra, subsequent history, etc.).
* Ambiguity is a warning, not a guess.

Usage
-----
    python3 bluebook_bot.py brief.txt                 # formatted text -> stdout, report -> stderr
    python3 bluebook_bot.py brief.txt -o final.md --toa
    cat research.txt | python3 bluebook_bot.py - --style underline
    python3 bluebook_bot.py brief.txt --json          # machine-readable
Exit code: 0 clean, 1 if any ERROR (or any WARN with --strict).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import date

OK, FIXED, WARN, ERROR = "OK", "FIXED", "WARN", "ERROR"
_RANK = {OK: 0, FIXED: 1, WARN: 2, ERROR: 3}

# --------------------------------------------------------------------------
# Italic markers (rendered per --style at the very end)
# --------------------------------------------------------------------------
I0, I1 = "\x01", "\x02"


def it(s: str) -> str:
    return f"{I0}{s}{I1}"


def plain(s: str) -> str:
    return s.replace(I0, "").replace(I1, "")


def render(s: str, style: str) -> str:
    a, b = {"markdown": ("*", "*"), "underline": ("_", "_"), "plain": ("", "")}[style]
    return s.replace(I0, a).replace(I1, b)


# --------------------------------------------------------------------------
# Reference tables
# --------------------------------------------------------------------------
REPORTERS = [
    "U.S.", "S. Ct.", "L. Ed.", "L. Ed. 2d",
    "F.2d", "F.3d", "F.4th", "F. App'x",
    "F. Supp.", "F. Supp. 2d", "F. Supp. 3d", "Fed. Cl.", "B.R.",
    "A.", "A.2d", "A.3d", "N.E.", "N.E.2d", "N.E.3d", "N.W.", "N.W.2d",
    "N.Y.S.", "N.Y.S.2d", "N.Y.S.3d", "P.", "P.2d", "P.3d",
    "S.E.", "S.E.2d", "S.W.", "S.W.2d", "S.W.3d",
    "So.", "So. 2d", "So. 3d", "Cal. Rptr.", "Cal. Rptr. 2d", "Cal. Rptr. 3d",
]
_key = lambda s: re.sub(r"[^a-z0-9]", "", s.lower())  # noqa: E731
REPORTER_BY_KEY = {_key(r): r for r in REPORTERS}

SCOTUS = {"U.S.", "S. Ct.", "L. Ed.", "L. Ed. 2d"}
YEAR_ONLY = SCOTUS | {"Fed. Cl."}
FED_APPELLATE = {"F.2d", "F.3d", "F.4th", "F. App'x"}
# (first year, last year) -- None = open ended. Used for WARN only.
REPORTER_YEARS = {
    "F.2d": (1924, 1993), "F.3d": (1993, 2021), "F.4th": (2021, None),
    "F. Supp.": (1932, 1998), "F. Supp. 2d": (1998, 2014), "F. Supp. 3d": (2014, None),
}

ABBREV = {
    "association": "Ass'n", "corporation": "Corp.", "company": "Co.", "incorporated": "Inc.",
    "limited": "Ltd.", "brothers": "Bros.", "department": "Dep't", "government": "Gov't",
    "commission": "Comm'n", "commissioner": "Comm'r", "railroad": "R.R.", "railway": "Ry.",
    "university": "Univ.", "national": "Nat'l", "international": "Int'l",
    "environmental": "Env't", "administration": "Admin.", "authority": "Auth.",
    "industries": "Indus.", "investment": "Inv.", "manufacturing": "Mfg.",
    "services": "Servs.", "service": "Serv.", "securities": "Sec.", "hospital": "Hosp.",
    "medical": "Med.", "community": "Cmty.", "education": "Educ.", "foundation": "Found.",
    "insurance": "Ins.", "savings": "Sav.", "federal": "Fed.", "employment": "Emp.",
    "committee": "Comm.", "products": "Prods.", "systems": "Sys.", "technology": "Tech.",
    "electric": "Elec.", "financial": "Fin.", "communications": "Commc'ns",
    "pharmaceutical": "Pharm.", "pharmaceuticals": "Pharms.",
    "inc": "Inc.", "co": "Co.", "corp": "Corp.", "ltd": "Ltd.", "bros": "Bros.",
}
SMALL_WORDS = {"of", "the", "and", "for", "de", "ex", "rel.", "on", "in", "a", "v."}
KEEP_UPPER = {"LLC", "LLP", "LP", "PLC", "NLRB", "EPA", "SEC", "FDA", "FCC", "IRS", "FTC",
              "FERC", "NAACP", "ACLU", "AFL-CIO", "USA", "NCAA", "OSHA"}
LEADINS = {"In", "Under", "As", "And", "But", "Because", "While", "When", "Per", "Thus",
           "Here", "Also", "Since", "If", "That", "Accord", "However", "Moreover", "Then"}

SIGNALS = {
    "see": "See", "see also": "See also", "see generally": "See generally", "cf.": "Cf.",
    "compare": "Compare", "accord": "Accord", "but see": "But see", "but cf.": "But cf.",
    "contra": "Contra", "see, e.g.,": "See, e.g.,", "e.g.,": "E.g.,",
}

RULE_SETS = {"app": "Fed. R. App. P.", "civ": "Fed. R. Civ. P.", "crim": "Fed. R. Crim. P.",
             "bankr": "Fed. R. Bankr. P.", "evid": "Fed. R. Evid."}

MONTHS = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?"

# --------------------------------------------------------------------------
# Regex construction
# --------------------------------------------------------------------------
SP = r"[ \t]+"
SPO = r"[ \t]*"


def _frag(canon: str) -> str:
    out = []
    for ch in canon:
        if ch == ".":
            out.append(r"\.?[ \t]?")
        elif ch == " ":
            out.append(r"[ \t]?")
        elif ch == "'":
            out.append(r"['’]?")
        else:
            out.append(re.escape(ch))
    return "".join(out)


REP = "(?:" + "|".join(_frag(c) for c in sorted(REPORTERS, key=len, reverse=True)) + ")"
LEAD = r"(?:[A-Z]|\d(?=\d*[A-Za-z]))"
TOK = r"(?:" + LEAD + r"[\w.'’&\-]*|of|the|and|for|de|ex|rel\.|on|in)"
W = TOK + ",?"
FIRST = LEAD + r"[\w.'’&\-]*,?"
PIN = r"\d{1,5}(?:" + SPO + r"[-–—]" + SPO + r"\d{1,5})?"
SIG = (r"(?:(?P<signal>(?i:see,?[ \t]e\.g\.,|see also|see generally|but see|but cf\.|see|cf\.|"
       r"compare|accord|contra|e\.g\.,))" + SP + ")?")

CASE_RE = re.compile(
    r"(?<![\w])(?!(?:Ibid|Id)\b)" + SIG +
    r"(?:(?P<name>" + FIRST + r"(?:" + SP + W + r"){0,6}?" + SP + r"[vV]s?\.?" + SP + W +
    r"(?:" + SP + W + r"){0,8}?)"
    r"|(?P<inre>(?:In" + SP + r"re|Ex" + SP + r"parte)" + SP + W + r"(?:" + SP + W + r"){0,6}?))"
    r",?" + SP + r"(?P<vol>\d{1,4})" + SP + r"(?P<rep>" + REP + r")" + SP + r"(?P<page>\d{1,5})"
    r"(?:(?:," + SPO + r"(?:at" + SP + r")?|" + SP + r"at" + SP + r")(?P<pin>" + PIN + r"))?"
    r"(?:" + SPO + r"\((?P<paren>[^()\n]*)\))?"
    r"(?P<extra>(?:" + SPO + r"\([^()\n]*\))*)"
)

SHORT_RE = re.compile(
    r"(?<![\w])" + SIG +
    r"(?P<name>" + FIRST.replace(",?", "") + r"(?:" + SP + TOK + r"){0,4}?)," + SP +
    r"(?P<vol>\d{1,4})" + SP + r"(?P<rep>" + REP + r")" + SP + r"at" + SP + r"(?P<pin>" + PIN + r")"
)

USC_RE = re.compile(
    r"(?<![\w.])(?P<title>\d{1,2})" + SPO + r"U\.?[ \t]?S\.?[ \t]?C\.?(?P<a>A)?\.?" + SPO +
    r"(?:§§?|sec\.?|section)?" + SPO +
    r"(?P<sec>\d+[a-z]{0,2}(?:-\d+[a-z]?)?)(?P<sub>(?:\([A-Za-z0-9]+\))*)"
    r"(?:" + SPO + r"\((?P<yr>(?:Supp\.[ \t]*[IVX]+[ \t]*)?\d{4})\))?"
)

CFR_RE = re.compile(
    r"(?<![\w.])(?P<title>\d{1,3})" + SPO + r"C\.?[ \t]?F\.?[ \t]?R\.?" + SPO +
    r"(?P<mark>§§?|pt\.?|part)?" + SPO +
    r"(?P<sec>\d+(?:\.\d+[a-z]?)?)(?P<sub>(?:\([A-Za-z0-9]+\))*)"
    r"(?:" + SPO + r"\((?P<yr>\d{4})\))?"
)

FEDREG_RE = re.compile(
    r"(?<![\w.])(?P<vol>\d{1,3})" + SPO + r"Fed\.?[ \t]?Reg\.?" + SPO + r"(?P<page>\d{1,6})"
    r"(?:," + SPO + r"(?P<pin>\d{1,6}))?(?:" + SPO + r"\((?P<date>[^()\n]+)\))?"
)

RULE_RE = re.compile(
    r"(?<![\w.])Fed\.?[ \t]?R\.?[ \t]?(?P<set>App|Civ|Crim|Evid|Bankr)\.?(?:[ \t]?P\.?)?" + SP +
    r"(?:Rule" + SP + r")?(?P<num>\d+(?:\([A-Za-z0-9]+\))*)"
)

CONST_RE = re.compile(
    r"(?<![\w.])U\.?[ \t]?S\.?[ \t]*Const(?:itution)?\.?,?" + SP +
    r"(?P<kind>amend|art)\.?" + SP + r"(?P<num>[IVXLC]+|\d{1,2})"
    r"(?:,?" + SPO + r"(?:§|sec\.?|section)" + SPO + r"(?P<sec>\d+))?"
    r"(?:,?" + SPO + r"cl\.?" + SPO + r"(?P<cl>\d+))?"
)

ID_RE = re.compile(
    r"(?<![\w.])(?P<id>Ibid\.?|[Ii]d\.|[Ii]d(?=[ \t]+at[ \t]+\d))"
    r"(?:" + SPO + r",?" + SPO + r"at" + SP + r"(?P<pin>" + PIN + r"))?"
)
WL_RE = re.compile(r"\b\d{4}[ \t]+(?:WL|U\.S\.[ \t]+(?:Dist|App)\.[ \t]+LEXIS)[ \t]+\d+")
SUPRA_RE = re.compile(r"\b[Ss]upra\b")
RECORD_RE = re.compile(r"\b(?:R\.|JA|ER|SER|Dkt\.|ECF[ \t]No\.)" + SPO + r"(?:at" + SPO + r")?\d+")

CIRCUIT_RE = re.compile(
    r"^(?:(?P<n>\d{1,2})[ \t]?(?:st|nd|rd|th|d)?[ \t]*Cir\.?|(?P<dc>D\.?[ \t]?C\.?)[ \t]*Cir\.?"
    r"|(?P<fed>Fed\.?)[ \t]*Cir\.?)$", re.I)
YEAR_RE = re.compile(r"(1[6-9]\d\d|20\d\d)")


# --------------------------------------------------------------------------
# Data model
# --------------------------------------------------------------------------
@dataclass
class Citation:
    kind: str
    start: int
    end: int
    original: str
    formatted: str | None = None  # contains italic markers
    status: str = OK
    notes: list[str] = field(default_factory=list)
    line: int = 0
    category: str = ""
    toa: str | None = None

    def raise_to(self, level: str, msg: str | None = None) -> None:
        if _RANK[level] > _RANK[self.status]:
            self.status = level
        if msg:
            self.notes.append(f"{level}: {msg}")

    def note(self, msg: str) -> None:
        self.notes.append(f"NOTE: {msg}")


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def fix_pin(p: str | None) -> str | None:
    """Rule 3.2(a): retain at least two digits when collapsing page ranges."""
    if not p:
        return p
    p = p.strip()
    m = re.fullmatch(r"(\d+)\s*[-–—]\s*(\d+)", p)
    if not m:
        return p
    a, b = m.groups()
    if len(b) < len(a):
        b = a[: len(a) - len(b)] + b
    if len(a) == len(b) and len(a) > 2:
        common = 0
        for x, y in zip(a, b):
            if x != y:
                break
            common += 1
        b = b[-max(2, len(b) - common):]
    return f"{a}–{b}"


def norm_signal(sig: str | None) -> str | None:
    if not sig:
        return None
    s = re.sub(r"\s+", " ", sig.strip().lower()).replace("see e.g.,", "see, e.g.,")
    canon = SIGNALS.get(s, sig.strip())
    if sig.strip()[0].islower():
        canon = canon[0].lower() + canon[1:]
    return canon


def _title_party(party: str) -> str:
    toks = party.split()
    out = []
    for i, t in enumerate(toks):
        core = t.rstrip(",")
        tail = t[len(core):]
        if core in KEEP_UPPER or re.fullmatch(r"(?:[A-Z]\.)+", core):
            out.append(t)
        elif core.lower() in SMALL_WORDS and i:
            out.append(core.lower() + tail)
        else:
            out.append(core.capitalize() + tail)
    return " ".join(out)


def _clean_party(party: str, notes: list[str], allcaps: bool = False) -> str:
    s = re.sub(r"\s+", " ", party).strip().rstrip(",")
    s = re.sub(r",?\s+et\s+al\.?", "", s)
    if allcaps:
        s = _title_party(s)
        notes.append("ALL-CAPS party name converted to title case; verify capitalization")
    if s.lower().startswith("the ") and len(s.split()) > 1:
        s = s[4:]
    s = re.sub(r"^United States of America$", "United States", s)
    out = []
    for t in s.split():
        core = t.rstrip(",.") if t.rstrip(",.").lower() in ABBREV else None
        if core is not None:
            tail = "," if t.endswith(",") else ""
            out.append(ABBREV[core.lower()] + tail)
        else:
            out.append(t)
    return " ".join(out)


def clean_case_name(raw: str, notes: list[str]) -> str:
    raw = re.sub(r"\s+", " ", raw).strip().rstrip(",")
    words = re.findall(r"[A-Za-z][A-Za-z.'’&\-]*", re.sub(r"\s[vV]s?\.?\s", " ", raw))
    caps = len(words) >= 3 and raw.upper() == raw
    m = re.match(r"^(In re|Ex parte)\s+(.*)$", raw, re.I)
    if m:
        lead = "In re" if m.group(1).lower() == "in re" else "Ex parte"
        return f"{lead} {_clean_party(m.group(2), notes, caps)}"
    parts = re.split(r"\s+[vV]s?\.?\s+", raw, maxsplit=1)
    if len(parts) == 2:
        return f"{_clean_party(parts[0], notes, caps)} v. {_clean_party(parts[1], notes, caps)}"
    return _clean_party(raw, notes, caps)


def strip_leadin(name: str, has_signal: bool) -> tuple[str, str]:
    """Return (verbatim lead-in text, remaining name)."""
    if has_signal:
        return "", name
    toks = name.split(" ")
    lead = []
    while len(toks) > 1 and toks[0] in LEADINS and toks[1].lower() not in ("re",):
        lead.append(toks.pop(0))
    return (" ".join(lead) + " " if lead else ""), " ".join(toks)


def parse_circuit(court: str) -> str | None:
    m = CIRCUIT_RE.match(court.strip())
    if not m:
        return None
    if m.group("n"):
        n = int(m.group("n"))
        if not 1 <= n <= 11:
            return None
        ordinal = {1: "1st", 2: "2d", 3: "3d"}.get(n, f"{n}th")
        return f"{ordinal} Cir."
    return "D.C. Cir." if m.group("dc") else "Fed. Cir."


def to_roman(n: int) -> str:
    vals = [(10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]
    out = ""
    for v, r in vals:
        while n >= v:
            out += r
            n -= v
    return out


# --------------------------------------------------------------------------
# Builders -- each returns a Citation (span, formatted, status, notes)
# --------------------------------------------------------------------------
def build_case(m: re.Match, text: str) -> Citation:
    notes_cleanup: list[str] = []
    sig = norm_signal(m.group("signal"))
    raw_name = m.group("name") or m.group("inre")
    lead, raw_name = ("", raw_name) if m.group("inre") else strip_leadin(raw_name, bool(sig))
    start = m.start("signal") if sig else m.start("name") if m.group("name") else m.start("inre")
    start += len(lead)
    c = Citation("case", start, m.end(), text[start:m.end()], category="Cases")
    name = clean_case_name(raw_name, notes_cleanup)
    for n in notes_cleanup:
        c.raise_to(WARN, n)

    rep = REPORTER_BY_KEY[_key(m.group("rep"))]
    vol, page = m.group("vol"), m.group("page")
    pin = fix_pin(m.group("pin"))
    paren = m.group("paren")
    extra = (m.group("extra") or "").strip()
    year = court = None

    if paren is None:
        c.raise_to(ERROR, "missing court/year parenthetical")
        pfmt = ""
    else:
        years = list(YEAR_RE.finditer(paren))
        if not years:
            c.raise_to(ERROR, "no year found in parenthetical")
            pfmt = f" ({paren.strip()})" if paren.strip() else ""
        else:
            ym = years[-1]
            year = ym.group(1)
            court = paren[: ym.start()].strip(" ,")
            if re.search(MONTHS + r"[ \t]+\d{1,2},?$", court):
                c.raise_to(WARN, "exact date given; Bluebook uses year only for reporter cites")
            if int(year) > date.today().year:
                c.raise_to(ERROR, f"year {year} is in the future")
            if paren[ym.end():].strip():
                c.raise_to(WARN, "unexpected text after year in parenthetical")
            if rep in YEAR_ONLY:
                if court and re.sub(r"[^a-z]", "", court.lower()) in ("us", "ussupct", "supct"):
                    court = ""
                elif court:
                    c.raise_to(WARN, f"court '{court}' is implied by reporter {rep}; omit if accurate")
            elif rep in FED_APPELLATE:
                circ = parse_circuit(court or "")
                if not court:
                    c.raise_to(ERROR, f"missing circuit for {rep} citation")
                elif circ:
                    court = circ
                else:
                    c.raise_to(WARN, f"unrecognized circuit '{court}'")
            elif not court:
                c.raise_to(ERROR, f"missing court/jurisdiction for {rep} citation")
            else:
                court = re.sub(r"\s+", " ", court)
            pfmt = f" ({court + ' ' if court else ''}{year})"

    rng = REPORTER_YEARS.get(rep)
    if rng and year:
        lo, hi = rng
        y = int(year)
        if y < lo or (hi is not None and y > hi):
            c.raise_to(WARN, f"{rep} does not normally cover {year}; check volume/year")
    if rep in ("S. Ct.", "L. Ed.", "L. Ed. 2d"):
        c.raise_to(WARN, "cite U.S. if the case is reported there (Rule 10.3.1)")
    if not pin:
        c.raise_to(WARN, "no pinpoint; pin cite the specific proposition (Rule 3.2)")
    after = text[m.end():m.end() + 40]
    if re.match(r"\s*,\s*(?:cert\.|aff['’]d|rev['’]d|vacated|overruled|appeal)", after, re.I):
        c.raise_to(WARN, "subsequent history follows; verify manually (Rule 10.7)")

    body = f"{it(name)}, {vol} {rep} {page}" + (f", {pin}" if pin else "") + pfmt
    if extra:
        body += " " + re.sub(r"\)\s*\(", ") (", extra)
    sigpart = (it(sig) + " ") if sig else ""
    c.formatted = sigpart + body
    c.toa = f"{it(name)}, {vol} {rep} {page}" + pfmt + (" " + extra if extra else "")
    return c


def build_short(m: re.Match, text: str) -> Citation:
    sig = norm_signal(m.group("signal"))
    lead, raw = strip_leadin(m.group("name"), bool(sig))
    start = (m.start("signal") if sig else m.start("name")) + len(lead)
    c = Citation("short", start, m.end(), text[start:m.end()], category="")
    notes: list[str] = []
    name = _clean_party(raw, notes)
    rep = REPORTER_BY_KEY[_key(m.group("rep"))]
    c.formatted = (it(sig) + " " if sig else "") + \
        f"{it(name)}, {m.group('vol')} {rep} at {fix_pin(m.group('pin'))}"
    c.note("short form; confirm a matching full citation appears earlier in the brief")
    return c


def build_usc(m: re.Match, text: str) -> Citation:
    c = Citation("usc", m.start(), m.end(), m.group(0), category="Statutes")
    f = f"{m.group('title')} U.S.C. § {m.group('sec')}{m.group('sub')}"
    c.toa = f"{m.group('title')} U.S.C. § {m.group('sec')}"
    if m.group("a"):
        c.raise_to(WARN, "cite U.S.C., not U.S.C.A./U.S.C.S., unless unofficial code is required (Rule 12.3)")
    if m.group("yr"):
        f += f" ({m.group('yr')})"
    else:
        c.note("no code year given; add edition year/Supp. if your court requires it (Rule 12.3.2)")
    if int(m.group("title")) > 54:
        c.raise_to(ERROR, f"U.S. Code has no Title {m.group('title')}")
    if int(m.group("title")) == 0:
        c.raise_to(ERROR, "invalid title 0")
    c.formatted = f
    return c


def build_cfr(m: re.Match, text: str) -> Citation:
    c = Citation("cfr", m.start(), m.end(), m.group(0), category="Regulations")
    mark = (m.group("mark") or "").lower()
    part = mark.startswith("pt") or mark == "part"
    pre = "pt." if part else "§"
    f = f"{m.group('title')} C.F.R. {pre} {m.group('sec')}{m.group('sub')}"
    c.toa = f"{m.group('title')} C.F.R. {pre} {m.group('sec')}"
    if m.group("yr"):
        f += f" ({m.group('yr')})"
    else:
        c.note("no year given; Rule 14.2 calls for the C.F.R. edition year")
    if not 1 <= int(m.group("title")) <= 50:
        c.raise_to(ERROR, f"C.F.R. has no Title {m.group('title')} (valid: 1-50)")
    c.formatted = f
    return c


def build_fedreg(m: re.Match, text: str) -> Citation:
    c = Citation("fedreg", m.start(), m.end(), m.group(0), category="Other Authorities")
    f = f"{m.group('vol')} Fed. Reg. {m.group('page')}"
    if m.group("pin"):
        f += f", {m.group('pin')}"
    if m.group("date"):
        f += f" ({m.group('date').strip()})"
    else:
        c.raise_to(WARN, "missing date parenthetical (Rule 14.2)")
    c.formatted = f
    c.toa = f"{m.group('vol')} Fed. Reg. {m.group('page')}" + (f" ({m.group('date').strip()})" if m.group("date") else "")
    return c


def build_rule(m: re.Match, text: str) -> Citation:
    c = Citation("rule", m.start(), m.end(), m.group(0), category="Rules")
    base = RULE_SETS[m.group("set").lower()]
    c.formatted = f"{base} {m.group('num')}"
    num = re.match(r"\d+", m.group("num")).group(0)
    c.toa = f"{base} {num}"
    return c


def build_const(m: re.Match, text: str) -> Citation:
    c = Citation("const", m.start(), m.end(), m.group(0), category="Constitutional Provisions")
    num = m.group("num")
    if num.isdigit():
        num = to_roman(int(num))
    kind = "amend." if m.group("kind") == "amend" else "art."
    f = f"U.S. Const. {kind} {num}"
    toa = f
    if m.group("sec"):
        f += f", § {m.group('sec')}"
        toa = f
    if m.group("cl"):
        f += f", cl. {m.group('cl')}"
    c.formatted, c.toa = f, toa
    return c


def build_id(m: re.Match, text: str) -> Citation:
    c = Citation("id", m.start(), m.end(), m.group(0), category="")
    if m.group("id").lower().startswith("ibid"):
        c.raise_to(ERROR, "'Ibid.' is not Bluebook form; use 'Id.' (Rule 4.1)")
        return c
    c.formatted = it("Id.") + (f" at {fix_pin(m.group('pin'))}" if m.group("pin") else "")
    return c


# --------------------------------------------------------------------------
# Engine
# --------------------------------------------------------------------------
def find_citations(text: str) -> list[Citation]:
    found: list[Citation] = []
    for rx, fn in ((CASE_RE, build_case), (SHORT_RE, build_short), (USC_RE, build_usc),
                   (CFR_RE, build_cfr), (FEDREG_RE, build_fedreg), (RULE_RE, build_rule),
                   (CONST_RE, build_const), (ID_RE, build_id)):
        for m in rx.finditer(text):
            # bare "id." followed by a lowercase word is prose, not a citation
            if fn is build_id and not m.group("pin") and re.match(r"[ \t]+[a-z]", text[m.end():m.end() + 2]):
                continue
            found.append(fn(m, text))
    for m in WL_RE.finditer(text):
        c = Citation("wl", m.start(), m.end(), m.group(0))
        c.raise_to(WARN, "Westlaw/Lexis cite: confirm docket no., court, and full date, "
                         "and that no reporter cite exists (Rule 10.8.1); left unchanged")
        found.append(c)
    for m in SUPRA_RE.finditer(text):
        c = Citation("supra", m.start(), m.end(), m.group(0))
        c.raise_to(WARN, "'supra' may not be used for cases, statutes, or rules (Rule 4.2); "
                         "use a short form or 'Id.'; left unchanged")
        found.append(c)
    for m in RECORD_RE.finditer(text):
        c = Citation("record", m.start(), m.end(), m.group(0))
        c.note("record cite; style is governed by the court's local rules; left unchanged")
        found.append(c)

    # resolve overlaps: earliest start wins, then longest
    found.sort(key=lambda c: (c.start, -(c.end - c.start)))
    kept: list[Citation] = []
    last_end = -1
    for c in found:
        if c.start >= last_end:
            kept.append(c)
            last_end = c.end
    for c in kept:
        c.line = text.count("\n", 0, c.start) + 1
        if c.formatted is not None and plain(c.formatted) != c.original and c.status == OK:
            c.status = FIXED
    return kept


def check_sequence(cites: list[Citation]) -> None:
    """Id. / short-form sanity checks across the document."""
    seen_authority = False
    for c in cites:
        if c.kind == "id":
            if not seen_authority:
                c.raise_to(ERROR, "'Id.' has no preceding authority")
        elif c.kind in ("case", "short", "usc", "cfr", "fedreg", "rule", "const"):
            seen_authority = True
    # short forms: require party name to appear in some earlier full case
    for i, c in enumerate(cites):
        if c.kind != "short":
            continue
        short_name = plain(c.formatted or "").split(",")[0]
        short_name = re.sub(r"^(?:See, e\.g\.,|See also|See generally|But see|But cf\.|See|Cf\.|"
                            r"Compare|Accord|Contra|E\.g\.,)\s+", "", short_name, flags=re.I)
        prior = [plain(p.formatted or "") for p in cites[:i] if p.kind == "case"]
        if not any(short_name.lower() in p.split(",")[0].lower() for p in prior):
            c.raise_to(WARN, f"no earlier full citation found for '{short_name}'")


@dataclass
class Result:
    text: str
    citations: list[Citation]


def analyze(text: str, style: str = "markdown", unwrap: bool = False) -> Result:
    text = text.replace("\u00a0", " ").replace("\r\n", "\n")
    if unwrap:
        text = re.sub(r"(?<!\n)\n(?!\n)", " ", text)
    cites = find_citations(text)
    check_sequence(cites)
    out, pos = [], 0
    for c in cites:
        out.append(text[pos:c.start])
        out.append(render(c.formatted, style) if c.formatted is not None else text[c.start:c.end])
        pos = c.end
    out.append(text[pos:])
    return Result("".join(out), cites)


def build_toa(cites: list[Citation], style: str) -> str:
    groups: dict[str, set[str]] = {}
    for c in cites:
        if c.toa and c.category:
            groups.setdefault(c.category, set()).add(c.toa)
    order = ["Cases", "Constitutional Provisions", "Statutes", "Regulations", "Rules",
             "Other Authorities"]
    lines = ["TABLE OF AUTHORITIES", "(page references must be added after final pagination)", ""]
    for cat in order:
        if cat in groups:
            lines.append(cat.upper())
            for e in sorted(groups[cat], key=lambda s: plain(s).lower()):
                lines.append("  " + render(e, style))
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def build_report(cites: list[Citation]) -> str:
    counts = {k: 0 for k in (OK, FIXED, WARN, ERROR)}
    for c in cites:
        counts[c.status] += 1
    lines = ["BLUEBOOK BUDDY REPORT", "=" * 60,
             f"{len(cites)} items | OK {counts[OK]} | FIXED {counts[FIXED]} | "
             f"WARN {counts[WARN]} | ERROR {counts[ERROR]}", ""]
    for c in cites:
        if c.status == OK and not c.notes:
            continue
        lines.append(f"[{c.status}] line {c.line} ({c.kind})")
        lines.append(f"    in : {c.original}")
        if c.formatted is not None and plain(c.formatted) != c.original:
            lines.append(f"    out: {plain(c.formatted)}")
        for n in c.notes:
            lines.append(f"    - {n}")
    lines.append("")
    lines.append("Verdict: " + ("FAIL (errors must be resolved)" if counts[ERROR]
                               else "PASS WITH WARNINGS (resolve manually)" if counts[WARN]
                               else "PASS"))
    lines.append("Reminder: this tool checks form, not substance. Cite-check every authority "
                 "(existence, pincite accuracy, subsequent history) before filing.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Format appellate-brief citations.")
    ap.add_argument("input", nargs="?", default="-", help="input file or '-' for stdin")
    ap.add_argument("-o", "--output", help="write formatted text here instead of stdout")
    ap.add_argument("--style", choices=["markdown", "underline", "plain"], default="markdown",
                    help="how italics are rendered (default: markdown *italics*)")
    ap.add_argument("--toa", action="store_true", help="append a Table of Authorities")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of text")
    ap.add_argument("--unwrap", action="store_true", help="join hard-wrapped lines before parsing")
    ap.add_argument("--strict", action="store_true", help="fail (exit 1) on warnings too")
    a = ap.parse_args(argv)

    raw = sys.stdin.read() if a.input == "-" else open(a.input, encoding="utf-8").read()
    res = analyze(raw, a.style, a.unwrap)
    worst = max((_RANK[c.status] for c in res.citations), default=0)

    if a.json:
        print(json.dumps([{
            "kind": c.kind, "line": c.line, "status": c.status, "original": c.original,
            "formatted": plain(c.formatted) if c.formatted is not None else None,
            "notes": c.notes} for c in res.citations], indent=2, ensure_ascii=False))
    else:
        body = res.text + ("\n\n" + build_toa(res.citations, a.style) if a.toa else "")
        if a.output:
            with open(a.output, "w", encoding="utf-8") as fh:
                fh.write(body)
        else:
            print(body)
        print(build_report(res.citations), file=sys.stderr)
    return 1 if worst >= _RANK[ERROR] or (a.strict and worst >= _RANK[WARN]) else 0


if __name__ == "__main__":
    sys.exit(main())
