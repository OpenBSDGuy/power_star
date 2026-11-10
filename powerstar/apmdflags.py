"""Edits of an apmd flags string (as stored by rcctl)."""

import re

_SLEEP = re.compile(r"^-([zZ])(\d*)$")


def _tokens(flags: str) -> list[tuple[str, str | None]]:
    """Split into (token, sleep value) where -z/-Z and their value become one entry."""
    toks, out, i = flags.split(), [], 0
    while i < len(toks):
        m = _SLEEP.match(toks[i])
        if m and not m.group(2) and i + 1 < len(toks):
            out.append((f"-{m.group(1)}", toks[i + 1]))
            i += 2
        else:
            out.append((toks[i], None))
            i += 1
    return out


def auto_sleep(flags: str) -> tuple[str | None, int | None]:
    result: tuple[str | None, int | None] = (None, None)
    for tok, val in _tokens(flags):
        m = _SLEEP.match(tok)
        if m:
            n = val if val is not None else m.group(2)
            if n.isdigit():
                result = ("suspend" if m.group(1) == "z" else "hibernate", int(n))
    return result


def with_auto_sleep(flags: str, mode: str | None, percent: int | None) -> str:
    kept = [t if v is None else f"{t} {v}" for t, v in _tokens(flags) if not _SLEEP.match(t)]
    if mode:
        kept.append(f"-{'z' if mode == 'suspend' else 'Z'} {percent}")
    return " ".join(kept)


def without_perf_flags(flags: str) -> str:
    kept = []
    for tok in flags.split():
        if re.fullmatch(r"-[A-Za-z]+", tok):
            tok = "-" + re.sub("[AHL]", "", tok[1:])
        if tok != "-":
            kept.append(tok)
    return " ".join(kept)
