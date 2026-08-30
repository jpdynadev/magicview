"""Protocol safety shim loaded automatically by Python's site module.

The Manabrew harness requires string-choice replies to be one of the exact tokens
advertised by Forge.  Older Kinnan policy code normalised color tokens to upper
case and, when it did not recognise the prompt's field name, could fall back to
an unavailable preferred color (for example ``U``).  That turns a legal game
state into an ENGINE_ERROR.

Keep the policy preference ordering, but when the prompt advertises choices:
1. discover them across the protocol field variants used by the harness;
2. compare using a canonical color symbol only for preference matching; and
3. return the *exact advertised token* rather than a normalised spelling.

This is deliberately a narrow runtime shim so the forensic gate can validate the
repair before any optimization search resumes.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def _choice_token(item: Any) -> str | None:
    """Return the exact protocol token represented by one advertised choice."""

    if isinstance(item, Mapping):
        # Prefer machine-facing values before human-facing labels.  Never
        # synthesize a value that was not present in the prompt.
        for key in ("value", "id", "token", "color", "name", "label"):
            value = item.get(key)
            if value is not None and str(value).strip():
                return str(value)
        return None
    if item is None:
        return None
    token = str(item)
    return token if token.strip() else None


def _canonical_color(token: str) -> str:
    value = token.strip().upper()
    if value.startswith("{") and value.endswith("}"):
        value = value[1:-1].strip()
    aliases = {
        "WHITE": "W",
        "BLUE": "U",
        "BLACK": "B",
        "RED": "R",
        "GREEN": "G",
        "COLORLESS": "C",
        "COLOURLESS": "C",
    }
    return aliases.get(value, value)


def _advertised_colors(inp: Mapping[str, Any]) -> list[str]:
    """Find the first non-empty exact choice list advertised by the prompt."""

    # ``availableColors``/``colors`` are used by color-specific prompts;
    # generic string-choice plumbing may expose the same legal set as
    # ``choices``, ``options`` or ``values``.
    for key in ("availableColors", "colors", "choices", "options", "values"):
        raw = inp.get(key)
        if not isinstance(raw, (list, tuple)) or not raw:
            continue
        tokens = [token for item in raw if (token := _choice_token(item)) is not None]
        if tokens:
            return tokens
    return []


def _install() -> None:
    try:
        import kinnan_policy_v8 as policy
    except Exception:
        # Other Python entry points in this repository do not necessarily put
        # engine-tests on sys.path.  In those processes this shim is a no-op.
        return

    original = policy.choose_payment_color

    def choose_payment_color_exact(inp: dict[str, Any], preferred: list[str]) -> str:
        offered = _advertised_colors(inp)
        if not offered:
            return original(inp, preferred)

        preferred_symbols = [_canonical_color(str(color)) for color in preferred]
        for wanted in preferred_symbols:
            for exact in offered:
                if _canonical_color(exact) == wanted:
                    return exact

        # A non-empty advertised legal set is authoritative.  Falling back to
        # its first exact token is always protocol-valid; emitting a preferred
        # color absent from that set is not.
        return offered[0]

    policy.choose_payment_color = choose_payment_color_exact


_install()
