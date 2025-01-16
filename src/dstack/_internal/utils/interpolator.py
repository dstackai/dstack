import string
from typing import Dict, Iterable, List, Literal, Optional, Tuple, Union, overload


class Pattern:
    opening = "${{"
    closing = "}}"


class Name:
    first_char = set(string.ascii_letters + "_")
    char = first_char | set(string.digits + ".")


class InterpolatorError(ValueError):
    pass


class VariablesInterpolator:
    def __init__(
        self, namespaces: Dict[str, Dict[str, str]], *, skip: Optional[Iterable[str]] = None
    ):
        self.skip = set(skip) if skip is not None else set()
        self.variables = {f"{ns}.{k}": v for ns in namespaces for k, v in namespaces[ns].items()}

    @overload
    def interpolate(self, s: str, return_missing: Literal[False] = False) -> str: ...

    @overload
    def interpolate(self, s: str, return_missing: Literal[True]) -> Tuple[str, List[str]]: ...

    def interpolate(
        self, s: str, return_missing: bool = False
    ) -> Union[str, Tuple[str, List[str]]]:
        tokens = []
        missing = []
        start = 0
        while start < len(s):
            dollar = s.find("$", start)
            if dollar == -1 or dollar == len(s) - 1:
                tokens.append(s[start:])
                break
            if s[dollar + 1] == "$":  # escaped $$
                tokens.append(s[start : dollar + 1])
                start = dollar + 2
                continue

            opening = s.find(Pattern.opening, start)
            if opening == -1:
                tokens.append(s[start:])
                break
            tokens.append(s[start:opening])
            closing = s.find(Pattern.closing, opening)
            if closing == -1:
                raise InterpolatorError(f"No pattern closing: {s[opening:]}")

            name = s[opening + len(Pattern.opening) : closing].strip()
            if not self.validate_name(name):
                raise InterpolatorError(f"Illegal reference name: {name}")
            if name.split(".")[0] in self.skip:
                tokens.append(s[opening : closing + len(Pattern.closing)])
            elif name in self.variables:
                tokens.append(self.variables[name])
            else:
                missing.append(name)
            start = closing + len(Pattern.closing)
        s = "".join(tokens)
        return (s, missing) if return_missing else s

    def interpolate_or_error(self, s: str) -> str:
        res, missing = self.interpolate(s, return_missing=True)
        if len(missing) == 0:
            return res
        raise InterpolatorError(f"Failed to interpolate due to missing vars: {missing}")

    @staticmethod
    def validate_name(s: str) -> bool:
        if s.count(".") != 1 or not (0 < s.index(".") < len(s) - 1):
            return False
        if s[0] not in Name.first_char or s[s.index(".") + 1] not in Name.first_char:
            return False
        if any((c not in Name.char) for c in s):
            return False
        return True
