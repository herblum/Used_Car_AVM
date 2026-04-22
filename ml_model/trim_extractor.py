"""Trim level extraction from version strings.

Three-tier extraction:
1. Brand-specific dictionary lookup (high-confidence known terms)
2. Fallback tokenization: strip technical terms, take first clean candidate
3. Return None if unparseable — LightGBM handles missing categoricals natively
"""

import re

import pandas as pd

# Brand → known trim terms, ordered by priority (longest/most specific first)
KNOWN_TRIMS: dict[str, list[str]] = {
    "volkswagen": [
        "comfortline", "highline", "sportline", "startline", "trendline",
        "r-line", "rline", "gti", "extreme", "luxury", "advance",
        "connect", "app", "united", "cross", "style", "life", "power",
    ],
    "ford": [
        "titanium+", "titanium", "wildtrak", "lariat", "limited",
        "raptor", "sel", "xlt", "xls", "xl", "st-line", "st",
        "ghia", "design", "active", "viral", "fly", "trend", "first",
    ],
    "toyota": [
        "gr-sport", "grsport", "limited", "platinum",
        "srx", "srv", "xei", "xls", "xli", "seg", "hev",
        "sr", "gr", "xs", "sx", "dx", "sport", "executive", "active",
    ],
    "chevrolet": [
        "midnight", "premier", "activ", "country", "classic",
        "ltz", "gls", "dlx", "joy", "high", "lt", "ls", "z71",
    ],
    "fiat": [
        "attractive", "precision", "trekking", "adventure", "sporting",
        "freedom", "volcano", "lounge", "absolute", "drive",
        "active", "sport", "like", "way", "top", "evo", "hgt", "fire",
    ],
    "renault": [
        "authentique", "expression", "dynamique", "privilege", "outsider",
        "initiale", "iconic", "intense", "intens", "evolution",
        "confort", "life", "zen", "bose",
    ],
    "peugeot": [
        "feline", "allure", "griffe", "generation", "premium",
        "active", "confort", "gt", "xs", "xt", "sv", "sport",
    ],
    "mercedes-benz": [
        "avantgarde", "progressive", "exclusive", "elegance",
        "amg-line", "amg", "urban", "night", "sport", "kompressor",
    ],
    "bmw": [
        "executive", "sportline", "sportive", "xline", "msport",
        "m sport", "luxury", "modern", "active", "sport",
    ],
    "audi": [
        "sportback", "ambition", "attraction", "ambiente",
        "prestige", "progressive", "cosmopolitan",
        "s-line", "sline", "advance", "sport",
    ],
    "jeep": [
        "trailhawk", "overland", "unlimited", "longitude",
        "limited", "rubicon", "summit", "serie-s",
        "sport",
    ],
    "honda": [
        "touring", "advanced", "ex-l", "exl", "exs", "lxs", "exr",
        "vti", "si", "lx", "ex",
    ],
    "nissan": [
        "exclusive", "advance", "acenta", "tekna", "visia",
        "sense", "pure", "play", "sr", "le", "xe", "bt",
    ],
    "kia": [
        "gt-line", "gtline", "exclusive", "premium", "pop", "gt", "ex",
    ],
    "hyundai": [
        "ultimate", "safety", "premium", "style", "gls", "gl",
    ],
    "ram": [
        "laramie", "limited", "rebel", "night", "sport", "slt",
    ],
    "mitsubishi": [
        "evolution", "hpe", "gls", "glx", "gsr", "sport",
    ],
    "dodge": [
        "hellcat", "laramie", "rebel", "srt", "sxt", "slt", "gtx",
    ],
    "porsche": [
        "carrera", "clubsport", "cabriolet", "cayman", "boxster",
        "targa", "gts", "gt",
    ],
    "chery": [
        "luxury", "comfort", "confort", "elite", "honor", "dignity", "light",
    ],
    "mini": [
        "chili", "pepper", "jcw", "cooper", "clubman", "hot",
    ],
    "suzuki": [
        "jlx", "gti", "glx", "jx", "xl",
    ],
    "subaru": [
        "limited", "sport", "gl", "gt", "xv", "xs",
    ],
    "land rover": [
        "autobiography", "dynamic", "hse", "sport", "se",
    ],
    "volvo": [
        "inscription", "r-design", "rdesign", "momentum", "luxury", "high",
    ],
    "lexus": [
        "f-sport", "fsport", "luxury", "executive",
    ],
    "alfa romeo": [
        "veloce", "progression", "distinctive", "quadrifoglio",
        "ti", "lusso", "super",
    ],
    "seat": [
        "cupra", "fr",
    ],
    "chrysler": [
        "limited", "gt",
    ],
    "gwm": [
        "dignity", "luxury", "elite", "deluxe", "honor",
    ],
    "baic": [
        "elite", "honor",
    ],
}

# Technical terms to filter during fallback extraction
TECHNICAL_TERMS: frozenset[str] = frozenset({
    # Transmissions
    "at", "mt", "cvt", "dsg", "tiptronic", "stronic", "multitronic",
    "automatico", "automatica", "automtica", "manual",
    # Drivetrain
    "4x4", "4x2", "4wd", "awd", "fwd", "rwd",
    "quattro", "xdrive", "sdrive",
    # Engine tech
    "tdi", "tsi", "tfsi", "hdi", "dci", "crdi", "vtec", "vvt", "mpi",
    "fsi", "thp", "tdci", "sce", "ecoboost", "gse", "gme", "msi",
    "multijet", "jtd", "tce", "bluehdi", "bluedci",
    "turbo", "biturbo", "twin",
    "v6", "v8", "v4", "v10", "i4", "boxer",
    # Unit labels
    "cv", "hp", "cc", "kw",
    # Body types (captured elsewhere)
    "sedan", "coupe", "cab", "doble", "cabina", "furgon", "pick", "up",
    "hatchback", "suv", "wagon", "minibus",
    # Generic / ambiguous
    "pack", "plus", "edition", "modelo", "new", "full", "base", "std",
    # Phase/gen codes
    "ph", "ph3", "ph2", "ph1", "eu4", "eu5", "eu6",
    # Short codes frequently misidentified as trims
    "cd", "cs", "gp", "sp", "gs", "rs", "sa", "na", "nr",
    "mio", "aa", "nac", "abs", "abs+",
    # Fuel types
    "diesel", "disel", "nafta", "gnc", "hybrid", "electrico",
    # Common but not trims
    "wd", "pas", "pasajeros", "cuero", "mixto",
})


def _build_trim_pattern(trim: str) -> re.Pattern:
    """Compile a word-boundary regex that tolerates hyphen/space variants."""
    escaped = re.escape(trim)
    # allow hyphen ↔ space interchangeability in multi-word trims
    escaped = escaped.replace(r"\-", r"[\-\s]?").replace(r"\ ", r"[\s\-]?")
    return re.compile(r"(?<![a-z])" + escaped + r"(?![a-z])")


# Pre-compile all patterns at import time
_TRIM_PATTERNS: dict[str, list[tuple[str, re.Pattern]]] = {
    marca: [(trim, _build_trim_pattern(trim)) for trim in trims]
    for marca, trims in KNOWN_TRIMS.items()
}

# Regex helpers for fallback
_RE_PURE_NUMBER = re.compile(r"^\d+\.?\d*$")
_RE_POWER = re.compile(r"^\d+\.?\d*(cv|hp|cc|kw|l)$")
_RE_AXLE = re.compile(r"^\d+x\d+$")
_RE_DIGIT_ALPHA = re.compile(r"^\d+[a-z]+$")       # 7as, 30a, 4x2
_RE_ALPHA_DIGIT = re.compile(r"^[a-z]+\d+[a-z]?$") # ph3, l20, b33, eu4
_RE_PHASE = re.compile(r"^ph\d+$")
_RE_ENGINE_SUFFIX = re.compile(r"^\d+\.?\d*[a-z]+$")  # 2.8l, 1600cc


def extract_trim(
    version: str | None,
    marca: str | None = None,
    modelo: str | None = None,  # noqa: ARG001 — reserved for future model-aware lookup
) -> str | None:
    """Extract trim level from a raw version string.

    Args:
        version: Raw version string, e.g. "2.8 Srx 177cv 4x4 7as At"
        marca:   Brand name for dictionary lookup, e.g. "toyota"
        modelo:  Model name (unused in Phase 1, reserved for future use)

    Returns:
        Normalized trim label (lowercase) or None if unparseable.

    Examples:
        >>> extract_trim("2.8 Srx 177cv 4x4", "toyota")
        'srx'
        >>> extract_trim("1.6 Trendline", "volkswagen")
        'trendline'
        >>> extract_trim("Titanium", "ford")
        'titanium'
        >>> extract_trim("5.7 Laramie Atx V8", "ram")
        'laramie'
        >>> extract_trim(None, "ford")
        None
    """
    if not version or pd.isna(version):
        return None

    version_lower = str(version).strip().lower()
    marca_lower = str(marca).strip().lower() if marca else None

    # --- Strategy 1: brand-specific dictionary (pre-compiled patterns) ---
    if marca_lower and marca_lower in _TRIM_PATTERNS:
        for trim, pattern in _TRIM_PATTERNS[marca_lower]:
            if pattern.search(version_lower):
                return trim

    # --- Strategy 2: tokenize + filter technical terms ---
    tokens = re.split(r"[\s/]+", version_lower)
    for raw_token in tokens:
        token = raw_token.strip(".,;:()[]")
        if not token or len(token) < 2:
            continue
        if _RE_PURE_NUMBER.match(token):
            continue
        if _RE_POWER.match(token):
            continue
        if _RE_AXLE.match(token):
            continue
        if _RE_DIGIT_ALPHA.match(token):
            continue
        if _RE_ALPHA_DIGIT.match(token):
            continue
        if _RE_PHASE.match(token):
            continue
        if _RE_ENGINE_SUFFIX.match(token) and not token.isalpha():
            continue
        if token in TECHNICAL_TERMS:
            continue
        return token

    return None


# ---------------------------------------------------------------------------
# Unit tests (run with: python trim_extractor.py)
# ---------------------------------------------------------------------------

def _run_tests() -> None:
    tests = [
        # (version, marca, expected)
        # --- Dictionary lookups ---
        ("2.8 Srx 177cv 4x4 7as At", "toyota", "srx"),
        ("2.8 Cd Gr-Sport 204Cv 4X4 At", "toyota", "gr-sport"),
        ("1.8 Xei Cvt 140cv", "toyota", "xei"),
        ("2.8 Cd Srv 177cv 4x4", "toyota", "srv"),
        ("1.6 Trendline 11b", "volkswagen", "trendline"),
        ("2.0 Cd Tdi 180cv 4x2 Highline", "volkswagen", "highline"),
        ("1.8 Turbo Gti", "volkswagen", "gti"),
        ("2.0 Exclusive Tsi 200cv Tiptronic", "volkswagen", "exclusive"),
        ("Titanium", "ford", "titanium"),
        ("2.5 Cd Ivct Xlt 166cv", "ford", "xlt"),
        ("3.5L V6 Ecoboost Lariat Luxury 4X4 At", "ford", "lariat"),
        ("1.6 Se Plus Powershift 120cv", "ford", "se"),
        ("5.7 Laramie Atx V8", "ram", "laramie"),
        ("2.0 Rebel Gme At9 4X4", "ram", "rebel"),
        ("1.4 Ltz Plus 153cv", "chevrolet", "ltz"),
        ("1.8 Activ Ltz 5as At 105cv", "chevrolet", "activ"),
        ("1.8 Adventure Alarma", "fiat", "adventure"),
        ("2.0 Freedom 4x4", "fiat", "freedom"),
        ("1.6 Authentique Pack I 90cv", "renault", "authentique"),
        ("1.6 Sce Evolution 156 Mt", "renault", "evolution"),
        ("1.6 Allure 156cv", "peugeot", "allure"),
        ("1.6 Feline Tiptronic", "peugeot", "feline"),
        ("2.0 C200 Kompressor Avantgarde", "mercedes-benz", "avantgarde"),
        ("1.8 C250 Avantgarde Sport At B.eff", "mercedes-benz", "avantgarde"),
        ("3.0 330i Executive Steptro.", "bmw", "executive"),
        ("3.0 Xdrive 35i Sportive 306cv", "bmw", "sportive"),
        ("3.2 Quattro Stronic", "audi", None),
        ("1.4 Tfsi Stronic Ambition 122cv", "audi", "ambition"),
        ("1.8 Sport", "jeep", "sport"),
        ("2.0 Td380 At9 4x4 7pas Limited", "jeep", "limited"),
        ("1.5 Lx Mt 120cv", "honda", "lx"),
        ("1.8 Exs At 140cv", "honda", "exs"),
        ("1.6 Advance 120cv", "nissan", "advance"),
        ("2.5 Exclusive Cvt Xtronic", "nissan", "exclusive"),
        ("1.3 T270 Longitude Plus At6", "jeep", "longitude"),
        # --- Fallback (unknown brand or no dict match) ---
        (None, "ford", None),
        ("", "toyota", None),
        ("1.6", "suzuki", None),
        ("V10", "ford", None),
        # --- Standalone trims ---
        ("Highline", "volkswagen", "highline"),
        ("Laramie", "ram", "laramie"),
        ("Comfortline", "volkswagen", "comfortline"),
    ]

    passed = 0
    failed = 0
    for version, marca, expected in tests:
        result = extract_trim(version, marca)
        ok = result == expected
        status = "PASS" if ok else "FAIL"
        if not ok:
            print(f"  {status}: extract_trim({version!r}, {marca!r})")
            print(f"           expected={expected!r}, got={result!r}")
            failed += 1
        else:
            passed += 1

    print(f"\n{passed}/{passed + failed} tests passed")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    _run_tests()
