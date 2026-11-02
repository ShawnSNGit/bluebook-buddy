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
* Access to Justice (A2J): Includes pro se / in forma pauperis assistance,
  free legal research links (CourtListener/LII/RECAP), full Spanish-language
  diagnostics (--lang es), accessibility/screen-reader optimization (--a11y),
  and spoken citation guides (--pronounce).

Usage
-----
    python3 bluebook_buddy.py brief.txt                 # formatted text -> stdout, report -> stderr
    python3 bluebook_buddy.py brief.txt -o final.md --toa
    python3 bluebook_buddy.py brief.txt --pro-se        # free research links & pro se guidance
    python3 bluebook_buddy.py brief.txt --lang es       # informe completo en español
    python3 bluebook_buddy.py brief.txt --a11y          # screen-reader & accessibility mode
    python3 bluebook_buddy.py brief.txt --pronounce     # spoken citation pronunciation guide
    cat research.txt | python3 bluebook_buddy.py - --style underline
    python3 bluebook_buddy.py brief.txt --json          # machine-readable
Exit code: 0 clean, 1 if any ERROR (or any WARN with --strict).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import date
from urllib.parse import quote_plus

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

SPANISH_SIGNALS = {
    "véase": "See", "vease": "See",
    "véase también": "See also", "vease tambien": "See also",
    "véase en general": "See generally", "vease en general": "See generally",
    "cf.": "Cf.", "cfr.": "Cf.",
    "compare": "Compare", "compare con": "Compare",
    "confróntese con": "Compare", "confrontese con": "Compare",
    "de acuerdo": "Accord", "acuerdo": "Accord",
    "pero véase": "But see", "pero vease": "But see",
    "pero cf.": "But cf.", "pero cfr.": "But cf.",
    "contra": "Contra",
    "véase, e.g.,": "See, e.g.,", "vease, e.g.,": "See, e.g.,",
    "véase, p. ej.,": "See, e.g.,", "vease, p. ej.,": "See, e.g.,",
    "véase p. ej.,": "See, e.g.,", "vease p. ej.,": "See, e.g.,",
    "p. ej.,": "E.g.,", "por ejemplo,": "E.g.,",
}

REPORTER_SPOKEN = {
    "U.S.": "United States Reports",
    "S. Ct.": "Supreme Court Reporter",
    "L. Ed.": "Lawyers' Edition",
    "L. Ed. 2d": "Lawyers' Edition, Second Series",
    "F.2d": "Federal Reporter, Second Series",
    "F.3d": "Federal Reporter, Third Series",
    "F.4th": "Federal Reporter, Fourth Series",
    "F. App'x": "Federal Appendix",
    "F. Supp.": "Federal Supplement",
    "F. Supp. 2d": "Federal Supplement, Second Series",
    "F. Supp. 3d": "Federal Supplement, Third Series",
    "Fed. Cl.": "Federal Claims Reporter",
    "B.R.": "Bankruptcy Reporter",
    "A.": "Atlantic Reporter",
    "A.2d": "Atlantic Reporter, Second Series",
    "A.3d": "Atlantic Reporter, Third Series",
    "N.E.": "North Eastern Reporter",
    "N.E.2d": "North Eastern Reporter, Second Series",
    "N.E.3d": "North Eastern Reporter, Third Series",
    "N.W.": "North Western Reporter",
    "N.W.2d": "North Western Reporter, Second Series",
    "N.Y.S.": "New York Supplement",
    "N.Y.S.2d": "New York Supplement, Second Series",
    "N.Y.S.3d": "New York Supplement, Third Series",
    "P.": "Pacific Reporter",
    "P.2d": "Pacific Reporter, Second Series",
    "P.3d": "Pacific Reporter, Third Series",
    "S.E.": "South Eastern Reporter",
    "S.E.2d": "South Eastern Reporter, Second Series",
    "S.W.": "South Western Reporter",
    "S.W.2d": "South Western Reporter, Second Series",
    "S.W.3d": "South Western Reporter, Third Series",
    "So.": "Southern Reporter",
    "So. 2d": "Southern Reporter, Second Series",
    "So. 3d": "Southern Reporter, Third Series",
    "Cal. Rptr.": "California Reporter",
    "Cal. Rptr. 2d": "California Reporter, Second Series",
    "Cal. Rptr. 3d": "California Reporter, Third Series",
}

COURT_SPOKEN = {
    "1st Cir.": "First Circuit Court of Appeals",
    "2d Cir.": "Second Circuit Court of Appeals",
    "3d Cir.": "Third Circuit Court of Appeals",
    "4th Cir.": "Fourth Circuit Court of Appeals",
    "5th Cir.": "Fifth Circuit Court of Appeals",
    "6th Cir.": "Sixth Circuit Court of Appeals",
    "7th Cir.": "Seventh Circuit Court of Appeals",
    "8th Cir.": "Eighth Circuit Court of Appeals",
    "9th Cir.": "Ninth Circuit Court of Appeals",
    "10th Cir.": "Tenth Circuit Court of Appeals",
    "11th Cir.": "Eleventh Circuit Court of Appeals",
    "D.C. Cir.": "District of Columbia Circuit Court of Appeals",
    "Fed. Cir.": "Federal Circuit Court of Appeals",
}

ROMAN_NUMS = {
    "I": "One", "II": "Two", "III": "Three", "IV": "Four", "V": "Five",
    "VI": "Six", "VII": "Seven", "VIII": "Eight", "IX": "Nine", "X": "Ten",
    "XI": "Eleven", "XII": "Twelve", "XIII": "Thirteen", "XIV": "Fourteen",
    "XV": "Fifteen", "XVI": "Sixteen", "XVII": "Seventeen", "XVIII": "Eighteen",
    "XIX": "Nineteen", "XX": "Twenty", "XXI": "Twenty-One", "XXII": "Twenty-Two",
    "XXIV": "Twenty-Four", "XXVI": "Twenty-Six", "XXVII": "Twenty-Seven",
}

ES_TRANSLATIONS = {
    "missing court/year parenthetical": "Falta el tribunal y el año entre paréntesis",
    "no year found in parenthetical": "No se encontró ningún año en el paréntesis",
    "exact date given; Bluebook uses year only for reporter cites": "Se incluyó la fecha exacta; Bluebook sólo utiliza el año para repertorios oficiales",
    "year is in the future": "El año está en el futuro",
    "unexpected text after year in parenthetical": "Texto inesperado tras el año en el paréntesis",
    "missing circuit for": "Falta el circuito federal de apelaciones para la cita",
    "missing court/jurisdiction for": "Falta el tribunal o la jurisdicción para la cita",
    "unrecognized circuit": "Circuito federal no reconocido",
    "cite U.S. if the case is reported there (Rule 10.3.1)": "Cite 'U.S.' si el caso está publicado allí (Regla 10.3.1)",
    "no pinpoint; pin cite the specific proposition (Rule 3.2)": "Sin número de página específico (pincite); cite la página exacta de la proposición (Regla 3.2)",
    "subsequent history follows; verify manually (Rule 10.7)": "Historial procesal posterior detectado; verifique manualmente (Regla 10.7)",
    "short form; confirm a matching full citation appears earlier in the brief": "Forma corta; confirme que exista una cita completa previa en el escrito",
    "cite U.S.C., not U.S.C.A./U.S.C.S., unless unofficial code is required (Rule 12.3)": "Cite U.S.C. (no U.S.C.A./U.S.C.S.), salvo que se exija el código no oficial (Regla 12.3)",
    "no code year given; add edition year/Supp. if your court requires it (Rule 12.3.2)": "No se indicó el año de la edición del código (Regla 12.3.2)",
    "missing date parenthetical (Rule 14.2)": "Falta el paréntesis con la fecha (Regla 14.2)",
    "'Ibid.' is not Bluebook form; use 'Id.' (Rule 4.1)": "'Ibid.' no es formato Bluebook; utilice 'Id.' (Regla 4.1)",
    "'Id.' has no preceding authority": "'Id.' no tiene ninguna autoridad previa a la que referirse",
    "ALL-CAPS party name converted to title case; verify capitalization": "Nombre de parte en MAYÚSCULAS convertido a tipo título; verifique la capitalización",
    "pro se court docket reference; standardized format": "Referencia a expediente judicial pro se; formato estandarizado",
    "Translated Spanish legal signal to Bluebook standard": "Señal legal en español traducida al estándar Bluebook",
    "Normalized Spanish constitutional reference to standard Bluebook citation": "Referencia constitucional en español normalizada a Bluebook",
    "Normalized Spanish statutory citation to standard U.S.C.": "Referencia legal en español normalizada a U.S.C.",
    "Normalized Spanish page indicator ('pág.') to standard comma pinpoint": "Indicador de página en español ('pág.') normalizado a coma estándar",
    "Westlaw/Lexis cite: confirm docket no., court, and full date": "Cita de Westlaw/Lexis: confirme núm. de expediente, tribunal y fecha completa",
    "'supra' may not be used for cases, statutes, or rules (Rule 4.2)": "'supra' no debe usarse para casos, estatutos o reglas (Regla 4.2)",
    "no earlier full citation found for": "No se encontró cita completa previa para",
}

PRO_SE_EXPLANATIONS = {
    "missing court/year parenthetical": "Why this matters: Courts require both the deciding court and the year so the judge knows who issued the decision and whether it is binding precedent.",
    "no pinpoint": "Why this matters: A 'pinpoint' (pincite) tells the judge exactly which page contains your quote or fact. Without it, busy judges may ignore the citation.",
    "missing circuit": "Why this matters: Federal appellate courts are divided into numbered circuits (1st through 11th, D.C., and Federal). The court must know which circuit decided your case.",
    "Ibid.": "Why this matters: In American legal writing, 'Ibid.' is forbidden. Always use 'Id.' when citing the authority immediately preceding.",
    "Westlaw/Lexis": "Why this matters: Paid database citations cost money to look up. Providing the official reporter or public docket number ensures anyone, including low-income filers, can access the case.",
    "short form": "Why this matters: A short citation (e.g., 'Brown, 347 U.S. at 495') is only allowed if you wrote out the full citation earlier in your document.",
    "subsequent history": "Why this matters: If a higher court modified, reversed, or affirmed this case, you must include that so the judge knows the decision is still valid law.",
}

PRO_SE_EXPLANATIONS_ES = {
    "missing court/year parenthetical": "Por qué es importante: Los tribunales exigen tanto el tribunal sentenciador como el año para saber qué tribunal emitió la decisión y si es un precedente vinculante.",
    "no pinpoint": "Por qué es importante: Una 'página específica' (pincite) le indica al juez exactamente en qué página está su cita o hecho relevante. Sin ella, el tribunal puede descartar la referencia.",
    "missing circuit": "Por qué es importante: Los tribunales federales de apelaciones se dividen en circuitos numerados (del 1.º al 11.º, D.C. y Federal). El tribunal necesita saber cuál resolvió el caso.",
    "Ibid.": "Por qué es importante: En los escritos legales de EE. UU. está prohibido 'Ibid.'. Utilice siempre 'Id.' cuando cite la misma autoridad inmediata anterior.",
    "Westlaw/Lexis": "Por qué es importante: Las citas de bases de datos de pago requieren suscripciones costosas. Usar el repertorio oficial o el número de expediente público permite que cualquier persona verifique el caso de forma gratuita.",
    "short form": "Por qué es importante: Una cita abreviada (ej. 'Brown, 347 U.S. at 495') sólo se permite si ya escribió la cita completa previamente en su escrito.",
    "subsequent history": "Por qué es importante: Si un tribunal superior modificó, revocó o confirmó el fallo, debe incluirse para asegurar que la decisión siga siendo derecho aplicable.",
}

HAINES_V_KERNER_NOTICE_EN = (
    "PRO SE FILING LEGAL PROTECTION (Rule of Lenity / Haines v. Kerner):\n"
    "\"A document filed pro se is 'to be liberally construed,' and 'a pro se complaint, "
    "however inartfully pleaded, must be held to less stringent standards than formal pleadings "
    "drafted by lawyers.'\"\n"
    "-- Haines v. Kerner, 404 U.S. 519, 520 (1972); accord Erickson v. Pardus, 551 U.S. 89, 94 (2007)."
)

HAINES_V_KERNER_NOTICE_ES = (
    "PROTECCIÓN LEGAL PARA LITIGANTES PRO SE (Doctrina Haines v. Kerner):\n"
    "\"Un documento presentado por una persona que se representa a sí misma (pro se) debe ser "
    "'interpretado con liberalidad', y 'una demanda pro se, por imperfectamente redactada que esté, "
    "debe sujetarse a normas menos rigurosas que los escritos formales redactados por abogados'.\"\n"
    "-- Haines v. Kerner, 404 U.S. 519, 520 (1972); conforme a Erickson v. Pardus, 551 U.S. 89, 94 (2007)."
)

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
       r"compare|accord|contra|e\.g\.,|"
       r"v[eé]ase,?[ \t]p\.?[ \t]?ej\.,?|"
       r"v[eé]ase[ \t]+tambi[eé]n|vease[ \t]+tambien|v[eé]ase[ \t]+en[ \t]+general|vease[ \t]+en[ \t]+general|"
       r"pero[ \t]+v[eé]ase|pero[ \t]+vease|pero[ \t]+cf\.|pero[ \t]+cfr\.|compare[ \t]+con|confr[oó]ntese[ \t]+con|"
       r"v[eé]ase|vease|cfr\.|p\.?[ \t]?ej\.,?|por[ \t]+ejemplo,?))" + SP + ")?")

CASE_RE = re.compile(
    r"(?<![\w])(?!(?:Ibid|Id)\b)" + SIG +
    r"(?:(?P<name>" + FIRST + r"(?:" + SP + W + r"){0,6}?" + SP + r"[vV]s?\.?" + SP + W +
    r"(?:" + SP + W + r"){0,8}?)"
    r"|(?P<inre>(?:In" + SP + r"re|Ex" + SP + r"parte)" + SP + W + r"(?:" + SP + W + r"){0,6}?))"
    r",?" + SP + r"(?P<vol>\d{1,4})" + SP + r"(?P<rep>" + REP + r")" + SP + r"(?P<page>\d{1,5})"
    r"(?:(?:," + SPO + r"(?:(?:at|p[aá]g\.?|p\.)" + SP + r")?|" + SP + r"(?:at|p[aá]g\.?|p\.)" + SP + r")(?P<pin>" + PIN + r"))?"
    r"(?:" + SPO + r"\((?P<paren>[^()\n]*)\))?"
    r"(?P<extra>(?:" + SPO + r"\([^()\n]*\))*)"
)

SHORT_RE = re.compile(
    r"(?<![\w])" + SIG +
    r"(?P<name>" + FIRST.replace(",?", "") + r"(?:" + SP + TOK + r"){0,4}?)," + SP +
    r"(?P<vol>\d{1,4})" + SP + r"(?P<rep>" + REP + r")" + SP + r"(?:at|p[aá]g\.?|p\.)" + SP + r"(?P<pin>" + PIN + r")"
)

USC_RE = re.compile(
    r"(?<![\w.])(?P<title>\d{1,2})" + SPO + r"(?:U\.?[ \t]?S\.?[ \t]?C\.?(?P<a>A)?\.?|C[oó]d\.?[ \t]+(?:de[ \t]+)?EE\.?[ \t]?UU\.?)" + SPO +
    r"(?:§§?|sec\.?|secci[oó]n|section)?" + SPO +
    r"(?P<sec>\d+[a-z]{0,2}(?:-\d+[a-z]?)?)(?P<sub>(?:\([A-Za-z0-9]+\))*)"
    r"(?:" + SPO + r"\((?P<yr>(?:Supp\.[ \t]*[IVX]+[ \t]*)?\d{4})\))?",
    re.I
)

CFR_RE = re.compile(
    r"(?<![\w.])(?P<title>\d{1,3})" + SPO + r"C\.?[ \t]?F\.?[ \t]?R\.?" + SPO +
    r"(?P<mark>§§?|pt\.?|part|parte|secci[oó]n|sec\.?)?" + SPO +
    r"(?P<sec>\d+(?:\.\d+[a-z]?)?)(?P<sub>(?:\([A-Za-z0-9]+\))*)"
    r"(?:" + SPO + r"\((?P<yr>\d{4})\))?",
    re.I
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
    r"(?<![\w.])(?:U\.?[ \t]?S\.?[ \t]*Const(?:itution)?\.?|"
    r"Const(?:ituci[oó]n)?[ \t]+(?:de[ \t]+(?:los[ \t]+)?(?:EE\.?[ \t]?UU\.?|Estados[ \t]+Unidos)|EE\.?[ \t]?UU\.?)),?" + SP +
    r"(?P<kind>amend|art|enmienda|art[ií]culo)\.?" + SP + r"(?P<num>[IVXLC]+|\d{1,2})"
    r"(?:,?" + SPO + r"(?:§|sec\.?|secci[oó]n|section)" + SPO + r"(?P<sec>\d+))?"
    r"(?:,?" + SPO + r"(?:cl\.?|cl[aá]usula)" + SPO + r"(?P<cl>\d+))?",
    re.I
)

ID_RE = re.compile(
    r"(?<![\w.])(?P<id>Ibid\.?|[Ii]d\.|[Ii]d(?=[ \t]+(?:at|p[aá]g\.?|p\.)[ \t]+\d))"
    r"(?:" + SPO + r",?" + SPO + r"(?:at|p[aá]g\.?|p\.)" + SP + r"(?P<pin>" + PIN + r"))?"
)
WL_RE = re.compile(r"\b\d{4}[ \t]+(?:WL|U\.S\.[ \t]+(?:Dist|App)\.[ \t]+LEXIS)[ \t]+\d+")
SUPRA_RE = re.compile(r"\b[Ss]upra\b")
RECORD_RE = re.compile(
    r"\b(?:(?:R\.|JA|ER|SER|PageID)[ \t]*(?:at[ \t]*)?\d+"
    r"|(?:ECF|Doc\.|Document|Dkt\.|Docket|Expediente)[ \t]*(?:No\.|Núm\.|Num\.)?[ \t]*(?:at[ \t]*)?\d+(?:[ \t]*,?[ \t]*(?:at|pág\.|pag\.|p\.)[ \t]*\d+)?"
    r"|(?:Ex\.|Exhibit)[ \t]+[A-Za-z0-9]+(?:[ \t]*,?[ \t]*(?:at|pág\.|pag\.|p\.)[ \t]*\d+)?)",
    re.I
)

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
    free_link: str | None = None
    pronunciation: str | None = None

    def raise_to(self, level: str, msg: str | None = None) -> None:
        if _RANK[level] > _RANK[self.status]:
            self.status = level
        if msg:
            self.notes.append(f"{level}: {msg}")

    def note(self, msg: str) -> None:
        self.notes.append(f"NOTE: {msg}")


# --------------------------------------------------------------------------
# Helpers & Translations
# --------------------------------------------------------------------------
def translate_note(note_str: str) -> str:
    level = ""
    for p in ("ERROR: ", "WARN: ", "NOTE: "):
        if note_str.startswith(p):
            level = {"ERROR: ": "ERROR: ", "WARN: ": "ADVERTENCIA: ", "NOTE: ": "NOTA: "}[p]
            note_str = note_str[len(p):]
            break
    for k, v in ES_TRANSLATIONS.items():
        if k.lower() in note_str.lower():
            return f"{level}{v}"
    return f"{level}{note_str}"


def get_pro_se_explanation(note_str: str, lang: str = "en") -> str | None:
    for k, v in PRO_SE_EXPLANATIONS.items():
        if k.lower() in note_str.lower():
            if lang == "es":
                return PRO_SE_EXPLANATIONS_ES.get(k, v)
            return v
    return None


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
    if s in SPANISH_SIGNALS:
        canon = SPANISH_SIGNALS[s]
    else:
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
# Free Research Links & Pronunciation Guides (A2J & A11y)
# --------------------------------------------------------------------------
def get_free_link(c: Citation) -> str | None:
    """Generate free, zero-cost public research URLs (CourtListener, Cornell LII, Federal Register)."""
    raw = plain(c.formatted or c.original)
    if c.kind in ("case", "short"):
        m = re.search(r"(\d+)\s+([A-Za-z0-9.\s']+?)\s+(?:at\s+)?(\d+)", raw)
        if m:
            vol, rep, page = m.group(1), m.group(2).strip(), m.group(3)
            if rep == "U.S.":
                return f"https://www.courtlistener.com/c/U.S./{vol}/{page}/"
            query = quote_plus(f"{vol} {rep} {page}")
            return f"https://www.courtlistener.com/?q={query}&type=o"
    elif c.kind == "usc":
        m = re.search(r"(\d+)\s+U\.S\.C\.\s+§\s+([\d\w]+)", raw)
        if m:
            return f"https://www.law.cornell.edu/uscode/text/{m.group(1)}/{m.group(2)}"
    elif c.kind == "cfr":
        m = re.search(r"(\d+)\s+C\.F\.R\.\s+(?:§|pt\.)\s+([\d\.]+)", raw)
        if m:
            return f"https://www.law.cornell.edu/cfr/text/{m.group(1)}/{m.group(2)}"
    elif c.kind == "fedreg":
        m = re.search(r"(\d+)\s+Fed\.\s+Reg\.\s+(\d+)", raw)
        if m:
            return f"https://www.federalregister.gov/documents/search?conditions[term]={m.group(1)}+FR+{m.group(2)}"
    elif c.kind == "const":
        m = re.search(r"U\.S\.\s+Const\.\s+(amend\.|art\.)\s+([IVXLC\d]+)", raw)
        if m:
            kind_str = "amendment" if "amend" in m.group(1) else "article"
            return f"https://www.law.cornell.edu/constitution/{kind_str}_{m.group(2).lower()}"
    elif c.kind == "rule":
        m = re.search(r"Fed\.\s+R\.\s+(Civ|App|Crim|Evid)\.\s+P\.\s+(\d+)", raw)
        if m:
            cat = {"Civ": "frcp", "App": "frap", "Crim": "frcrmp", "Evid": "fre"}.get(m.group(1), "frcp")
            return f"https://www.law.cornell.edu/rules/{cat}/rule_{m.group(2)}"
    return None


def pronounce_citation(c: Citation) -> str:
    """Generate plain-English spoken pronunciation guide for oral arguments, screen-readers, and TTS."""
    raw = plain(c.formatted or c.original)
    if c.kind in ("case", "short"):
        m = re.match(
            r"^(?P<name>.*?),\s+(?P<vol>\d+)\s+(?P<rep>.*?)\s+(?:at\s+)?(?P<page>\d+)(?:,\s+(?P<pin>\d+(?:[–-]\d+)?))?(?:\s+\((?P<paren>.*?)\))?",
            raw
        )
        if m:
            name = m.group("name").replace(" v. ", " versus ")
            vol = m.group("vol")
            rep = m.group("rep").strip()
            page = m.group("page")
            pin = m.group("pin")
            paren = m.group("paren") or ""
            rep_sp = REPORTER_SPOKEN.get(rep, rep)
            parts = [f"{name}, Volume {vol}, {rep_sp}, page {page}"]
            if pin:
                if "–" in pin or "-" in pin:
                    p1, p2 = re.split(r"[–-]", pin)
                    parts.append(f"at pages {p1} through {p2}")
                else:
                    parts.append(f"at page {pin}")
            if paren:
                yr_match = re.search(r"(\d{4})", paren)
                yr = yr_match.group(1) if yr_match else paren
                court_part = paren[:yr_match.start()].strip() if yr_match else ""
                court_sp = COURT_SPOKEN.get(court_part, court_part)
                if court_sp:
                    parts.append(f"decided by the {court_sp} in {yr}")
                else:
                    parts.append(f"decided in {yr}")
            return ", ".join(parts) + "."
    elif c.kind == "usc":
        m = re.match(r"^(\d+)\s+U\.S\.C\.\s+§\s+([\d\w\-]+(?:\([A-Za-z0-9]+\))*)", raw)
        if m:
            return f"Title {m.group(1)}, United States Code, Section {m.group(2)}."
    elif c.kind == "cfr":
        m = re.match(r"^(\d+)\s+C\.F\.R\.\s+(?:§|pt\.)\s+([\d\.\w\-]+(?:\([A-Za-z0-9]+\))*)", raw)
        if m:
            return f"Title {m.group(1)}, Code of Federal Regulations, Section {m.group(2)}."
    elif c.kind == "fedreg":
        m = re.match(r"^(\d+)\s+Fed\.\s+Reg\.\s+(\d+)", raw)
        if m:
            return f"Volume {m.group(1)}, Federal Register, page {m.group(2)}."
    elif c.kind == "const":
        m = re.match(r"^U\.S\.\s+Const\.\s+(amend\.|art\.)\s+([IVXLC\d]+)(?:,\s+§\s+(\d+))?(?:,\s+cl\.\s+(\d+))?", raw)
        if m:
            kind_word = "Amendment" if "amend" in m.group(1) else "Article"
            num = m.group(2)
            word = ROMAN_NUMS.get(num, num)
            res = f"United States Constitution, {kind_word} {num} ({word})"
            if m.group(3):
                res += f", Section {m.group(3)}"
            if m.group(4):
                res += f", Clause {m.group(4)}"
            return res + "."
    elif c.kind == "rule":
        return f"{raw}."
    elif c.kind == "record":
        return f"Court record reference: {raw}."
    return f"{raw}."


# --------------------------------------------------------------------------
# Builders -- each returns a Citation (span, formatted, status, notes)
# --------------------------------------------------------------------------
def build_case(m: re.Match, text: str) -> Citation:
    notes_cleanup: list[str] = []
    sig_raw = m.group("signal")
    sig = norm_signal(sig_raw)
    raw_name = m.group("name") or m.group("inre")
    lead, raw_name = ("", raw_name) if m.group("inre") else strip_leadin(raw_name, bool(sig))
    start = m.start("signal") if sig else m.start("name") if m.group("name") else m.start("inre")
    start += len(lead)
    c = Citation("case", start, m.end(), text[start:m.end()], category="Cases")
    name = clean_case_name(raw_name, notes_cleanup)
    if sig_raw and sig_raw.strip().lower() in SPANISH_SIGNALS:
        notes_cleanup.append("Translated Spanish legal signal to Bluebook standard")
    if m.group("pin") and any(p in text[m.start():m.end()].lower() for p in ("pág", "pag.")):
        notes_cleanup.append("Normalized Spanish page indicator ('pág.') to standard comma pinpoint")
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
    sig_raw = m.group("signal")
    sig = norm_signal(sig_raw)
    lead, raw = strip_leadin(m.group("name"), bool(sig))
    start = (m.start("signal") if sig else m.start("name")) + len(lead)
    c = Citation("short", start, m.end(), text[start:m.end()], category="")
    notes: list[str] = []
    name = _clean_party(raw, notes)
    if sig_raw and sig_raw.strip().lower() in SPANISH_SIGNALS:
        notes.append("Translated Spanish legal signal to Bluebook standard")
    rep = REPORTER_BY_KEY[_key(m.group("rep"))]
    c.formatted = (it(sig) + " " if sig else "") + \
        f"{it(name)}, {m.group('vol')} {rep} at {fix_pin(m.group('pin'))}"
    c.note("short form; confirm a matching full citation appears earlier in the brief")
    for n in notes:
        c.raise_to(WARN, n)
    return c


def build_usc(m: re.Match, text: str) -> Citation:
    c = Citation("usc", m.start(), m.end(), m.group(0), category="Statutes")
    f = f"{m.group('title')} U.S.C. § {m.group('sec')}{m.group('sub')}"
    c.toa = f"{m.group('title')} U.S.C. § {m.group('sec')}"
    raw_lower = m.group(0).lower()
    if any(w in raw_lower for w in ("cód", "cod.", "código")):
        c.note("Normalized Spanish statutory citation to standard U.S.C.")
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
    part = mark.startswith("pt") or mark.startswith("part") or mark.startswith("parte")
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
    kind_raw = m.group("kind").lower()
    is_spanish = any(w in m.group(0).lower() for w in ("constitución", "constitucion", "ee.uu", "enmienda", "artículo", "articulo", "cláusula", "clausula"))
    kind = "amend." if kind_raw.startswith("amend") or kind_raw.startswith("enmienda") else "art."
    f = f"U.S. Const. {kind} {num}"
    toa = f
    if m.group("sec"):
        f += f", § {m.group('sec')}"
        toa = f
    if m.group("cl"):
        f += f", cl. {m.group('cl')}"
    c.formatted, c.toa = f, toa
    if is_spanish:
        c.note("Normalized Spanish constitutional reference to standard Bluebook citation")
    return c


def build_id(m: re.Match, text: str) -> Citation:
    c = Citation("id", m.start(), m.end(), m.group(0), category="")
    if m.group("id").lower().startswith("ibid"):
        c.raise_to(ERROR, "'Ibid.' is not Bluebook form; use 'Id.' (Rule 4.1)")
        return c
    c.formatted = it("Id.") + (f" at {fix_pin(m.group('pin'))}" if m.group("pin") else "")
    return c


def build_record(m: re.Match, text: str) -> Citation:
    c = Citation("record", m.start(), m.end(), m.group(0))
    raw = m.group(0).strip()
    m_ecf = re.match(r"(?i)^(ecf|doc|dkt|docket)\.?\s*(?:no\.|núm\.|num\.)?\s*(\d+)(?:,?\s*(?:at|pág\.|pag\.|p\.)\s*(\d+))?$", raw)
    if m_ecf:
        prefix = "ECF No." if m_ecf.group(1).lower() in ("ecf",) else "Doc." if m_ecf.group(1).lower() in ("doc", "document") else "Dkt."
        num = m_ecf.group(2)
        pin = m_ecf.group(3)
        formatted = f"{prefix} {num}" + (f", at {pin}" if pin else "")
        if formatted != raw:
            c.formatted = formatted
    c.note("pro se court docket reference; standardized format")
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
        found.append(build_record(m, text))

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
        c.free_link = get_free_link(c)
        c.pronunciation = pronounce_citation(c)
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


def build_toa(cites: list[Citation], style: str, lang: str = "en") -> str:
    is_es = lang == "es"
    groups: dict[str, set[str]] = {}
    for c in cites:
        if c.toa and c.category:
            groups.setdefault(c.category, set()).add(c.toa)
    order = ["Cases", "Constitutional Provisions", "Statutes", "Regulations", "Rules",
             "Other Authorities"]
    cat_names = {
        "Cases": "CASOS" if is_es else "CASES",
        "Constitutional Provisions": "DISPOSICIONES CONSTITUCIONALES" if is_es else "CONSTITUTIONAL PROVISIONS",
        "Statutes": "ESTATUTOS" if is_es else "STATUTES",
        "Regulations": "REGLAMENTOS" if is_es else "REGULATIONS",
        "Rules": "REGLAS PROCESALES" if is_es else "RULES",
        "Other Authorities": "OTRAS AUTORIDADES" if is_es else "OTHER AUTHORITIES",
    }
    title = "TABLA DE AUTORIDADES" if is_es else "TABLE OF AUTHORITIES"
    subtitle = ("(las referencias de página deben agregarse tras la paginación final)"
                if is_es else "(page references must be added after final pagination)")
    lines = [title, subtitle, ""]
    for cat in order:
        if cat in groups:
            lines.append(cat_names.get(cat, cat.upper()))
            for e in sorted(groups[cat], key=lambda s: plain(s).lower()):
                lines.append("  " + render(e, style))
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def build_report(
    cites: list[Citation],
    lang: str = "en",
    pro_se: bool = False,
    a11y: bool = False,
    pronounce: bool = False,
    links: bool = False,
) -> str:
    is_es = lang == "es"
    counts = {k: 0 for k in (OK, FIXED, WARN, ERROR)}
    for c in cites:
        counts[c.status] += 1

    status_names = {
        OK: "CORRECTO" if is_es else OK,
        FIXED: "CORREGIDO" if is_es else FIXED,
        WARN: "ADVERTENCIA" if is_es else WARN,
        ERROR: "ERROR" if is_es else ERROR,
    }

    if a11y:
        # Screen-reader / assistive technology optimized structure (semantic headings, no decorative ASCII art)
        title = "# Informe de Accesibilidad de BlueBook Buddy" if is_es else "# BlueBook Buddy Accessibility Report"
        lines = [title, ""]
        lines.append("## " + ("Resumen Ejecutivo" if is_es else "Executive Summary"))
        lines.append(f"- {'Total de autoridades analizadas' if is_es else 'Total authorities analyzed'}: {len(cites)}")
        lines.append(f"- {status_names[OK]}: {counts[OK]}")
        lines.append(f"- {status_names[FIXED]}: {counts[FIXED]}")
        lines.append(f"- {status_names[WARN]}: {counts[WARN]}")
        lines.append(f"- {status_names[ERROR]}: {counts[ERROR]}")
        lines.append("")

        if counts[ERROR]:
            verdict_str = ("FALLO (Existen errores que deben corregirse antes de la presentación)"
                           if is_es else "FAIL (Errors must be resolved before court filing)")
        elif counts[WARN]:
            verdict_str = ("APROBADO CON ADVERTENCIAS (Revise las observaciones manualmente)"
                           if is_es else "PASS WITH WARNINGS (Review items manually)")
        else:
            verdict_str = ("APROBADO (Todas las citas cumplen con las normas Bluebook)"
                           if is_es else "PASS (All citations adhere to Bluebook standards)")
        lines.append(f"**{'Veredicto' if is_es else 'Verdict'}:** {verdict_str}")
        lines.append("")

        lines.append("## " + ("Detalle de Citas Analizadas" if is_es else "Detailed Citation Analysis"))
        for i, c in enumerate(cites, 1):
            lines.append(f"### {'Cita' if is_es else 'Citation'} {i}: {'Línea' if is_es else 'Line'} {c.line} ({c.kind})")
            lines.append(f"- **{'Texto original' if is_es else 'Original'}**: `{c.original}`")
            if c.formatted is not None and plain(c.formatted) != c.original:
                lines.append(f"- **{'Texto corregido' if is_es else 'Formatted'}**: `{plain(c.formatted)}`")
            lines.append(f"- **{'Estado' if is_es else 'Status'}**: {status_names[c.status]}")

            if (pronounce or a11y) and c.pronunciation:
                lines.append(f"- **{'Pronunciación sugerida / Lectura oral' if is_es else 'Spoken Read-Aloud Guide'}**: {c.pronunciation}")

            if (links or pro_se or a11y) and c.free_link:
                lines.append(f"- **{'Enlace de acceso público gratuito' if is_es else 'Free Public Access Link'}**: {c.free_link}")

            if c.notes:
                lines.append(f"- **{'Observaciones' if is_es else 'Notes'}**:")
                for n in c.notes:
                    note_disp = translate_note(n) if is_es else n
                    lines.append(f"  - {note_disp}")
                    if pro_se or a11y:
                        expl = get_pro_se_explanation(n, lang=lang)
                        if expl:
                            lines.append(f"    * {expl}")
            lines.append("")

        if pro_se or a11y:
            lines.append("## " + ("Protección Legal para Litigantes Pro Se" if is_es else "Legal Notice for Pro Se Filers"))
            lines.append(HAINES_V_KERNER_NOTICE_ES if is_es else HAINES_V_KERNER_NOTICE_EN)
            lines.append("")

        lines.append("## " + ("Recordatorio de Verificación" if is_es else "Verification Reminder"))
        reminder = (
            "Esta herramienta evalúa la forma y el formato, no la vigencia ni el fondo sustantivo. "
            "Verifique la existencia, el número de página específico y el historial procesal antes de presentar su documento ante el tribunal."
            if is_es else
            "This tool evaluates citation form, not judicial substance. Always verify existence, "
            "pinpoint accuracy, and subsequent history before submitting documents to court."
        )
        lines.append(reminder)
        return "\n".join(lines)

    # Standard terminal / plain-text report
    header_title = "INFORME DE BLUEBOOK BUDDY" if is_es else "BLUEBOOK BUDDY REPORT"
    item_str = "elementos" if is_es else "items"
    lines = [
        header_title,
        "=" * 60,
        f"{len(cites)} {item_str} | {status_names[OK]} {counts[OK]} | {status_names[FIXED]} {counts[FIXED]} | "
        f"{status_names[WARN]} {counts[WARN]} | {status_names[ERROR]} {counts[ERROR]}",
        "",
    ]
    for c in cites:
        if c.status == OK and not c.notes and not (pro_se or links or pronounce):
            continue
        line_word = "línea" if is_es else "line"
        lines.append(f"[{status_names[c.status]}] {line_word} {c.line} ({c.kind})")
        lines.append(f"    in : {c.original}")
        if c.formatted is not None and plain(c.formatted) != c.original:
            lines.append(f"    out: {plain(c.formatted)}")
        if (pronounce or pro_se) and c.pronunciation:
            lbl = "hablado: " if is_es else "spoken: "
            lines.append(f"    {lbl}{c.pronunciation}")
        if (links or pro_se) and c.free_link:
            lbl = "gratis : " if is_es else "free   : "
            lines.append(f"    {lbl}{c.free_link}")
        for n in c.notes:
            note_disp = translate_note(n) if is_es else n
            lines.append(f"    - {note_disp}")
            if pro_se:
                expl = get_pro_se_explanation(n, lang=lang)
                if expl:
                    lines.append(f"      [{expl}]")

    lines.append("")
    verdict_lbl = "Veredicto: " if is_es else "Verdict: "
    if counts[ERROR]:
        v_msg = "FALLO (los errores deben resolverse antes de presentar)" if is_es else "FAIL (errors must be resolved)"
    elif counts[WARN]:
        v_msg = "APROBADO CON ADVERTENCIAS (revisar manualmente)" if is_es else "PASS WITH WARNINGS (resolve manually)"
    else:
        v_msg = "APROBADO" if is_es else "PASS"
    lines.append(f"{verdict_lbl}{v_msg}")

    if pro_se:
        lines.append("")
        lines.append("-" * 60)
        lines.append(HAINES_V_KERNER_NOTICE_ES if is_es else HAINES_V_KERNER_NOTICE_EN)

    lines.append("")
    reminder = (
        "Recordatorio: Esta herramienta verifica la forma, no el fondo. Verifique cada autoridad "
        "(existencia, precisión de la página específica, historial procesal posterior) antes de presentar su escrito."
        if is_es else
        "Reminder: this tool checks form, not substance. Cite-check every authority "
        "(existence, pincite accuracy, subsequent history) before filing."
    )
    lines.append(reminder)
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
    ap.add_argument("--pro-se", "--low-income", dest="pro_se", action="store_true",
                    help="pro se / in forma pauperis mode: includes free research links (CourtListener/LII), plain-English explanations, and Haines v. Kerner notice")
    ap.add_argument("--links", "--free-links", dest="links", action="store_true",
                    help="include direct free public legal research links (CourtListener, Cornell LII) for all authorities")
    ap.add_argument("--lang", choices=["en", "es"], default="en",
                    help="report language: 'en' for English, 'es' for Spanish (Español)")
    ap.add_argument("--a11y", "--screen-reader", dest="a11y", action="store_true",
                    help="accessibility mode: screen-reader optimized headings, no repetitive ASCII dividers, structured semantics")
    ap.add_argument("--pronounce", "--speak", dest="pronounce", action="store_true",
                    help="include spoken/read-aloud phonetic pronunciation guide for oral arguments and screen readers")
    a = ap.parse_args(argv)

    raw = sys.stdin.read() if a.input == "-" else open(a.input, encoding="utf-8").read()
    res = analyze(raw, a.style, a.unwrap)
    worst = max((_RANK[c.status] for c in res.citations), default=0)

    if a.json:
        print(json.dumps([{
            "kind": c.kind, "line": c.line, "status": c.status, "original": c.original,
            "formatted": plain(c.formatted) if c.formatted is not None else None,
            "notes": c.notes,
            "free_link": c.free_link,
            "pronunciation": c.pronunciation,
        } for c in res.citations], indent=2, ensure_ascii=False))
    else:
        body = res.text + ("\n\n" + build_toa(res.citations, a.style, a.lang) if a.toa else "")
        if a.output:
            with open(a.output, "w", encoding="utf-8") as fh:
                fh.write(body)
        else:
            print(body)
        print(build_report(
            res.citations,
            lang=a.lang,
            pro_se=a.pro_se,
            a11y=a.a11y,
            pronounce=a.pronounce,
            links=a.links,
        ), file=sys.stderr)
    return 1 if worst >= _RANK[ERROR] or (a.strict and worst >= _RANK[WARN]) else 0


if __name__ == "__main__":
    sys.exit(main())
