from powerstar.system import Result, System


class FakeSystem(System):
    """Records commands; answers from `responses`, keyed by the exact argv tuple."""

    def __init__(self, responses: dict[tuple[str, ...], "Result | str | Exception"] | None = None, files: dict | None = None):
        self.responses = responses or {}
        self.files = files or {}
        self.calls: list[list[str]] = []

    def run(self, argv, check=True):
        from powerstar.errors import PowerStarError

        self.calls.append(list(argv))
        r = self.responses[tuple(argv)]  # KeyError for unexpected commands
        if isinstance(r, Exception):
            raise r
        r = Result(0, r, "") if isinstance(r, str) else r
        if check and r.rc != 0:
            raise PowerStarError(f"{argv[0]} failed", detail=r.err)
        return r

    def read_file(self, path):
        return self.files.get(str(path))
