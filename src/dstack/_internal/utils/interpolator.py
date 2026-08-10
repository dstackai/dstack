import string
from collections.abc import Mapping
from typing import Callable, Iterable, List, Literal, Optional, Tuple, Union, overload

NameValidator = Callable[[str], bool]


class Pattern:
    opening = "${{"
    closing = "}}"


class Name:
    first_char = set(string.ascii_letters + "_")
    char = first_char | set(string.digits + ".")


class InterpolatorError(ValueError):
    """
    Raised when interpolation fails.

    May be shown to the users, should not contain sensitive information,
    such as variable values.
    """

    pass


def namespace_root(name: str) -> str:
    """Return the namespace of a ref name, e.g. groups[0].nodes[0].IP_ADDRESS -> groups."""
    return name.split(".")[0].split("[")[0]


class VariablesInterpolator:
    def __init__(
        self,
        namespaces: Mapping[str, Mapping[str, str]],
        *,
        skip: Optional[Union[Iterable[str], Mapping[str, NameValidator]]] = None,
    ):
        # Iterable[str] keeps old callers working and uses validate_name.
        # Mapping[str, validator] lets callers plug feature-specific rules.
        if skip is None:
            self.skip_validators: dict[str, NameValidator] = {}
        elif isinstance(skip, Mapping):
            self.skip_validators = dict(skip)
        else:
            self.skip_validators = {ns: self.validate_name for ns in skip}
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
            # Skip before validate_name so deferred refs can be left for later
            # interpolators. Invalid skipped names still raise.
            skip_ns = namespace_root(name)
            if skip_ns in self.skip_validators:
                if not self.skip_validators[skip_ns](name):
                    raise InterpolatorError(f"Illegal reference name: {name}")
                tokens.append(s[opening : closing + len(Pattern.closing)])
            elif not self.validate_name(name):
                raise InterpolatorError(f"Illegal reference name: {name}")
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
