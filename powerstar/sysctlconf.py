"""Line-level edits of /etc/sysctl.conf text; every untouched byte is kept."""

import re


def _active(key: str) -> re.Pattern:
    return re.compile(rf"^(\s*){re.escape(key)}\s*=\s*([^#\n]*?)\s*(#.*)?$")


def _lines(text: str) -> list[str]:
    return text.split("\n")


def current_value(text: str, key: str) -> str | None:
    pat, val = _active(key), None
    for line in _lines(text):
        m = pat.match(line.rstrip("\r"))
        if m:
            val = m.group(2)
    return val


def disable_key(text: str, key: str) -> str:
    pat = _active(key)
    return "\n".join(f"# disabled by powerstar: {l}" if pat.match(l) else l for l in _lines(text))


def set_value(text: str, key: str, value: str) -> str:
    if current_value(text, key) == value:
        return text
    pat = _active(key)
    lines = _lines(text)
    idx = [i for i, l in enumerate(lines) if pat.match(l)]
    if not idx:
        sep = "" if text == "" or text.endswith("\n") else "\n"
        return f"{text}{sep}# added by powerstar\n{key}={value}\n"
    for i in idx[:-1]:
        lines[i] = f"# disabled by powerstar: {lines[i]}"
    m = pat.match(lines[idx[-1]])
    comment = f" {m.group(3)}" if m.group(3) else ""
    lines[idx[-1]] = f"{m.group(1)}{key}={value}{comment}"
    return "\n".join(lines)
