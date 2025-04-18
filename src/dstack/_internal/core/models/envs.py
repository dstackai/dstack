import re
from typing import Dict, Iterable, Iterator, List, Mapping, NamedTuple, Tuple, Union, cast

from pydantic import BaseModel, Field, validator
from typing_extensions import Annotated, Self

from dstack._internal.core.models.common import CoreModel

# VAR_NAME=VALUE, VAR_NAME=, or VAR_NAME
_ENV_STRING_REGEX = r"^([a-zA-Z_][a-zA-Z0-9_]*)(=.*$|$)"


class EnvSentinel(CoreModel):
    key: str

    def from_env(self, env: Mapping[str, str]) -> str:
        if self.key in env:
            return env[self.key]
        raise ValueError(f"Environment variable {self.key} is not set")

    def __str__(self):
        return f"EnvSentinel({self.key})"


class EnvVarTuple(NamedTuple):
    key: str
    value: Union[str, EnvSentinel]

    @classmethod
    def parse(cls, v: str) -> Self:
        r = re.match(_ENV_STRING_REGEX, v)
        if r is None:
            raise ValueError(v)
        if "=" in v:
            key, value = v.split("=", 1)
        else:
            key = r.group(1)
            value = EnvSentinel(key=key)
        return cls(key, value)


class Env(BaseModel):
    """
    Env represents a mapping of process environment variables, as in environ(7).
    Environment values may be omitted, in that case the :class:`EnvSentinel`
    object is used as a placeholder.

    To create an instance from a `dict[str, str]` or a `list[str]` use pydantic's
    :meth:`BaseModel.parse_obj(dict | list)` method.

    NB: this is *NOT* a CoreModel, pydantic-duality, which is used as a base
    for the CoreModel, doesn't play well with custom root models.
    """

    __root__: Union[
        List[Annotated[str, Field(regex=_ENV_STRING_REGEX)]],
        Dict[str, Union[str, EnvSentinel]],
    ] = {}

    @validator("__root__")
    def validate_root(cls, v: Union[List[str], Dict[str, str]]) -> Dict[str, str]:
        if isinstance(v, list):
            d = {}
            for var in v:
                if "=" not in var:
                    if var not in d:
                        d[var] = EnvSentinel(key=var)
                    else:
                        raise ValueError(f"Duplicate environment variable: {var}")
                else:
                    k, val = var.split("=", maxsplit=1)
                    if k not in d:
                        d[k] = val
                    else:
                        raise ValueError(f"Duplicate environment variable: {var}")
            return d
        # TODO: apply the same validation rules to dict keys as for keys in the list form;
        # validate values (must be strings).
        return v

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self._dict})"

    def __str__(self) -> str:
        return str(self._dict)

    def __iter__(self) -> Iterator[str]:
        return iter(self._dict)

    def __contains__(self, item: str) -> bool:
        return item in self._dict

    def __len__(self) -> int:
        return len(self._dict)

    def __getitem__(self, item):
        return self._dict[item]

    def __setitem__(self, item, value):
        self._dict[item] = value

    def copy(self, **kwargs) -> Self:
        # Env.copy() is tricky because it copies only the hidden top-level {"__root__": {...}}
        # structure, not the actual nested dict representing the env itself.
        # So we copy __root__ explicitly in case of a shallow copy.
        new_copy = super().copy(**kwargs)
        if not kwargs.get("deep", False):
            new_copy.__root__ = new_copy.__root__.copy()
        return new_copy

    def as_dict(self) -> Dict[str, str]:
        """
        Returns env variables as a new dict asserting that all values
        are resolved.

        :raises ValueError: Not all variables are resolved.
        """
        unresolved: List[str] = []
        dct: Dict[str, str] = {}
        for k, v in self.items():
            if isinstance(v, EnvSentinel):
                unresolved.append(k)
            else:
                # cast is required since TypeGuard is for positive cases only
                dct[k] = cast(str, v)
        if unresolved:
            unresolved_repr = ", ".join(sorted(unresolved))
            raise ValueError(f"not all variables are resolved: {unresolved_repr}")
        return dct

    def update(self, env_or_map: Union[Self, Mapping[str, Union[str, EnvSentinel]]]) -> None:
        if isinstance(env_or_map, type(self)):
            self._dict.update(env_or_map._dict)
        else:
            self._dict.update(env_or_map)

    def keys(self) -> Iterable[str]:
        return self._dict.keys()

    def values(self) -> Iterable[Union[str, EnvSentinel]]:
        return self._dict.values()

    def items(self) -> Iterable[Tuple[str, Union[str, EnvSentinel]]]:
        return self._dict.items()

    @property
    def _dict(self) -> Dict[str, Union[str, EnvSentinel]]:
        # this property is redundant for runtime and used for _proper_ type signature only
        return cast(Dict, self.__root__)
