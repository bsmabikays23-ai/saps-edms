"""
classifier.py — Rules-based case classification engine for SAPS eDMS.

Reads a Case and returns:
  • tier             — one of the four classification tiers
  • recommended_unit — the unit best suited to investigate
  • reasons          — a list of human-readable strings explaining the decision

The engine is deterministic: the same case always classifies the same way.
No machine learning, no external API, no randomness.
"""

import re
from typing import Iterable


# ---------------------------------------------------------------------------
# Tier definitions
# ---------------------------------------------------------------------------
TIER_LIGHT      = "Light / Routine"
TIER_SMALL      = "Small / Standard"
TIER_SERIOUS    = "Serious / Complex"
TIER_PRIORITY   = "Priority / Highly Complex"

TIERS = [TIER_LIGHT, TIER_SMALL, TIER_SERIOUS, TIER_PRIORITY]


# ---------------------------------------------------------------------------
# Base score per crime type (0–10 scale)
# ---------------------------------------------------------------------------
CRIME_BASE_SCORE = {
    "Theft":           1,
    "Housebreaking":   2,
    "Fraud":           3,
    "Assault":         3,
    "Drug Offence":    4,
    "Robbery":         6,
    "Hijacking":       7,
    "Murder":          9,
    "Other":           3,
}


# ---------------------------------------------------------------------------
# Keyword weights — scanned against the description text
# ---------------------------------------------------------------------------
KEYWORD_WEIGHTS = {
    # Violent / weapon indicators
    r"\bgun\b":             4,
    r"\bfirearm\b":         4,
    r"\bpistol\b":          4,
    r"\brifle\b":           4,
    r"\bknife\b":           3,
    r"\bmachete\b":         3,
    r"\bpanga\b":           3,
    r"\barmed\b":           3,
    r"\bweapon\b":          3,
    r"\bshot\b":            4,
    r"\bstabbed\b":         4,
    r"\bassault(ed)?\b":    3,
    r"\battack(ed)?\b":     3,
    r"\bthreat(ened)?\b":   2,
    r"\bwounded\b":         3,
    r"\binjur(ed|ies)\b":   3,

    # Multiple persons
    r"\bgang\b":            5,
    r"\bgroup of\b":        3,
    r"\bmultiple (suspects|victims)\b": 5,
    r"\bthree men\b":       3,
    r"\btwo men\b":         2,
    r"\bfour men\b":        3,
    r"\baccomplices\b":     3,
    r"\bcrew\b":            3,

    # Organised / syndicate indicators
    r"\bsyndicate\b":       6,
    r"\borganis(ed|ation)\b": 5,
    r"\bsmuggling\b":       5,
    r"\btrafficking\b":     6,
    r"\bcartel\b":          7,
    r"\bracket\b":          5,
    r"\bhijack(ing)?\b":    4,
    r"\bkidnap(ping)?\b":   6,
    r"\bextort(ion)?\b":    5,
    r"\bmoney laundering\b": 6,

    # Vulnerable victims
    r"\bchild\b":           6,
    r"\bminor\b":           5,
    r"\binfant\b":          6,
    r"\bbaby\b":            5,
    r"\belderly\b":         4,
    r"\bdisabled\b":        4,
    r"\bwoman\b":           2,
    r"\brape\b":            8,
    r"\bsexual\b":          7,
    r"\bdomestic\b":        4,
    r"\babuse\b":           5,

    # Financial / commercial
    r"\bmillion\b":         6,
    r"\bR\d{5,}\b":         4,
    r"\bfraud\b":           4,
    r"\bscam\b":            3,
    r"\bembezzl(e|ement)\b": 6,
    r"\bcorrupt(ion)?\b":   6,
    r"\bbribe(ry)?\b":      5,
    r"\bfinancial\b":       3,

    # Death / serious harm
    r"\bdeath\b":           7,
    r"\bdead\b":            7,
    r"\bmurder(ed)?\b":     9,
    r"\bkill(ed)?\b":       7,
    r"\bhomicide\b":        8,
    r"\bbody\b":            5,
    r"\bcorpse\b":          6,
}


# ---------------------------------------------------------------------------
# Unit mapping — which unit handles which crime type / tier
# ---------------------------------------------------------------------------
CRIME_TO_UNIT = {
    "Hijacking":     "Serious & Violent Crime",
    "Murder":        "Serious & Violent Crime",
    "Robbery":       "Serious & Violent Crime",
    "Assault":       "Serious & Violent Crime",
    "Fraud":         "Commercial Crime",
    "Drug Offence":  "Organised Crime",
}

TIER_TO_UNIT_FALLBACK = {
    TIER_LIGHT:     "General Detective",
    TIER_SMALL:     "General Detective",
    TIER_SERIOUS:   "Serious & Violent Crime",
    TIER_PRIORITY:  "DPCI / Hawks",
}


# ---------------------------------------------------------------------------
# Tier thresholds (from total score)
# ---------------------------------------------------------------------------
TIER_THRESHOLDS = [
    (3,  TIER_LIGHT),      # score 0–3
    (7,  TIER_SMALL),      # score 4–7
    (12, TIER_SERIOUS),    # score 8–12
    (10**9, TIER_PRIORITY) # score 13+
]


def _score_to_tier(score: int) -> str:
    for threshold, tier in TIER_THRESHOLDS:
        if score <= threshold:
            return tier
    return TIER_PRIORITY


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
def classify_case(crime_type: str,
                  description: str,
                  financial_value: float = None,
                  num_suspects: int = None,
                  weapons: Iterable[str] = None) -> dict:
    """
    Classify a case and return:
      {
        "tier": str,
        "score": int,
        "recommended_unit": str,
        "reasons": [str, ...],
      }
    """
    reasons = []
    score = 0

    # ---- 1. Crime type base score ----
    base = CRIME_BASE_SCORE.get(crime_type or "Other", 3)
    score += base
    reasons.append(f"Crime type '{crime_type}' contributes a base score of {base}.")

    # ---- 2. Keywords from the description ----
    text = (description or "").lower()
    matched_terms = []
    for pattern, weight in KEYWORD_WEIGHTS.items():
        if re.search(pattern, text, re.IGNORECASE):
            score += weight
            matched_terms.append((pattern, weight))

    if matched_terms:
        # Sort by weight so the strongest indicators show first
        matched_terms.sort(key=lambda x: -x[1])
        top = matched_terms[:5]  # show up to five strongest
        human = ", ".join(f"{_clean_pattern(p)} (+{w})" for p, w in top)
        reasons.append(f"Description keywords detected: {human}.")
    else:
        reasons.append("No significant keywords detected in the description.")

    # ---- 3. Financial value ----
    if financial_value:
        fv = float(financial_value)
        if fv >= 1_000_000:
            score += 8
            reasons.append(f"Financial value of R{fv:,.0f} adds 8 (large-scale loss).")
        elif fv >= 100_000:
            score += 5
            reasons.append(f"Financial value of R{fv:,.0f} adds 5 (significant loss).")
        elif fv >= 10_000:
            score += 3
            reasons.append(f"Financial value of R{fv:,.0f} adds 3 (material loss).")
        elif fv > 0:
            score += 1
            reasons.append(f"Financial value of R{fv:,.0f} adds 1.")

    # ---- 4. Number of suspects ----
    if num_suspects:
        try:
            ns = int(num_suspects)
        except (TypeError, ValueError):
            ns = 0
        if ns >= 5:
            score += 6
            reasons.append(f"{ns} suspects involved adds 6 (group activity).")
        elif ns >= 3:
            score += 4
            reasons.append(f"{ns} suspects involved adds 4.")
        elif ns == 2:
            score += 2
            reasons.append("2 suspects involved adds 2.")
        elif ns == 1:
            score += 0
            reasons.append("1 suspect — no extra weight.")

    # ---- 5. Weapons ----
    weapons_list = [w for w in (weapons or []) if w]
    if weapons_list:
        # Each weapon adds 3, capped at 8 total
        weapon_score = min(8, 3 * len(weapons_list))
        score += weapon_score
        reasons.append(
            f"Weapons recorded ({', '.join(weapons_list)}) adds {weapon_score}."
        )

    # ---- 6. Tier decision ----
    tier = _score_to_tier(score)
    reasons.append(f"Total score {score} places this case in '{tier}'.")

    # ---- 7. Recommended unit ----
    unit = None

    # Priority tier always goes to DPCI / Hawks
    if tier == TIER_PRIORITY:
        unit = "DPCI / Hawks"
        reasons.append("Priority tier routes to DPCI / Hawks.")

    # Serious tier: prefer crime-type specialised unit, else Serious & Violent
    elif tier == TIER_SERIOUS:
        unit = CRIME_TO_UNIT.get(crime_type) or "Serious & Violent Crime"
        reasons.append(f"Serious tier routes to {unit}.")

    # Otherwise use the crime-type mapping, else fall back by tier
    else:
        unit = CRIME_TO_UNIT.get(crime_type) or TIER_TO_UNIT_FALLBACK[tier]
        reasons.append(f"Standard routing sends this case to {unit}.")

    # Special overrides — crime type trumps tier for specialised units
    if crime_type == "Fraud" and "Commercial" not in (unit or ""):
        unit = "Commercial Crime"
        reasons.append("Fraud crimes always route to Commercial Crime.")
    if crime_type == "Drug Offence" and tier in (TIER_SERIOUS, TIER_PRIORITY):
        unit = "Organised Crime"
        reasons.append("Serious drug offences route to Organised Crime.")

    return {
        "tier": tier,
        "score": score,
        "recommended_unit": unit,
        "reasons": reasons,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _clean_pattern(pattern: str) -> str:
    """Turn a regex like r'\\bgun\\b' into a human-friendly 'gun'."""
    s = pattern.replace(r"\b", "").replace("\\b", "")
    s = s.replace("(", "").replace(")", "")
    s = s.replace("?", "")
    s = s.strip()
    return s


def classify(case) -> dict:
    """
    Convenience wrapper that takes a Case model instance and returns the
    same dict as classify_case(). Parses weapons_involved from the DB string.
    """
    weapons = []
    if getattr(case, "weapons_involved", None):
        weapons = [w.strip() for w in case.weapons_involved.split(",") if w.strip()]

    return classify_case(
        crime_type=case.crime_type,
        description=case.description,
        financial_value=case.financial_value,
        num_suspects=case.num_suspects,
        weapons=weapons,
    )