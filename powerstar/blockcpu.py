"""hw.blockcpu letters: S (SMT), P, E, L core types the scheduler avoids."""

ORDER = "SPEL"


def blocked(value: str) -> set[str]:
    return set(value) & set(ORDER)


def compose(current: str, wanted: set[str], present: set[str]) -> str:
    keep = {l for l in blocked(current) if l not in present}
    return "".join(l for l in ORDER if l in keep or (l in present and l in wanted))


def problem(wanted: set[str], present: set[str]) -> str | None:
    cores = present - {"S"}
    if cores and cores <= wanted:
        return "This would leave only one CPU running"
    return None
