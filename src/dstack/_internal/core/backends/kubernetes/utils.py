import ast
from typing import Any, Callable, List, Literal, Optional, TypeVar, Union, get_origin, overload

import yaml
from kubernetes import client as kubernetes_client
from kubernetes import config as kubernetes_config
from typing_extensions import ParamSpec

T = TypeVar("T")
P = ParamSpec("P")


def get_api_from_config_data(kubeconfig_data: str) -> kubernetes_client.CoreV1Api:
    config_dict = yaml.load(kubeconfig_data, yaml.FullLoader)
    return get_api_from_config_dict(config_dict)


def get_api_from_config_dict(kubeconfig: dict) -> kubernetes_client.CoreV1Api:
    api_client = kubernetes_config.new_client_from_config_dict(config_dict=kubeconfig)
    return kubernetes_client.CoreV1Api(api_client=api_client)


@overload
def call_api_method(
    method: Callable[P, Any],
    type_: type[T],
    expected: None = None,
    *args: P.args,
    **kwargs: P.kwargs,
) -> T: ...


@overload
def call_api_method(
    method: Callable[P, Any],
    type_: type[T],
    expected: Union[int, tuple[int, ...], list[int]],
    *args: P.args,
    **kwargs: P.kwargs,
) -> Optional[T]: ...


def call_api_method(
    method: Callable[P, Any],
    type_: type[T],
    expected: Optional[Union[int, tuple[int, ...], list[int]]] = None,
    *args: P.args,
    **kwargs: P.kwargs,
) -> Optional[T]:
    """
    Returns the result of the API method call, optionally ignoring specified HTTP status codes.

    Args:
        method: the `CoreV1Api` bound method.
        type_: The expected type of the return value, used for runtime type checking and
            as a type hint for a static type checker (as kubernetes package is not type-annotated).
            NB: For composite types, only "origin" type is checked, e.g., list, not list[Node]
        expected: Expected error statuses, e.g., 404.
        args: positional arguments of the method.
        kwargs: keyword arguments of the method.
    Returns:
        The return value or `None` in case of the expected error.
    """
    if isinstance(expected, int):
        expected = (expected,)
    result: T
    try:
        result = method(*args, **kwargs)
    except kubernetes_client.ApiException as e:
        if expected is None or e.status not in expected:
            raise
        return None
    if not isinstance(result, get_origin(type_) or type_):
        raise TypeError(
            f"{method.__name__} returned {type(result).__name__}, expected {type_.__name__}"
        )
    return result


@overload
def get_value(
    obj: object, path: str, type_: type[T], *, required: Literal[False] = False
) -> Optional[T]: ...


@overload
def get_value(obj: object, path: str, type_: type[T], *, required: Literal[True]) -> T: ...


def get_value(obj: object, path: str, type_: type[T], *, required: bool = False) -> Optional[T]:
    """
    Returns the value at a given path.
    Supports object attributes, sequence indices, and mapping keys.

    Args:
        obj: The object to traverse.
        path: The path to the value, regular Python syntax. The leading dot is optional, all the
            following are correct: `.attr`, `attr`, `.[0]`, `[0]`, `.['key']`, `['key']`.
        type_: The expected type of the value, used for runtime type checking and as a type hint
            for a static type checker (as kubernetes package is not type-annotated).
            NB: For composite types, only "origin" type is checked, e.g., list, not list[Node]
        required: If `True`, the value must exist and must not be `None`. If `False` (safe
            navigation mode), the may not exist and may be `None`.

    Returns:
        The requested value or `None` in case of failed traverse when required=False.
    """
    _path = path.removeprefix(".")
    if _path.startswith("["):
        src = f"obj{_path}"
    else:
        src = f"obj.{_path}"
    module = ast.parse(src)
    assert len(module.body) == 1, ast.dump(module, indent=4)
    root_expr = module.body[0]
    assert isinstance(root_expr, ast.Expr), ast.dump(module, indent=4)
    varname: Optional[str] = None
    expr = root_expr.value
    while True:
        if isinstance(expr, ast.Name):
            varname = expr.id
            break
        if __debug__:
            if isinstance(expr, ast.Subscript):
                if isinstance(expr.slice, ast.UnaryOp):
                    # .items[-1]
                    assert isinstance(expr.slice.op, ast.USub), ast.dump(expr, indent=4)
                    assert isinstance(expr.slice.operand, ast.Constant), ast.dump(expr, indent=4)
                    assert isinstance(expr.slice.operand.value, int), ast.dump(expr, indent=4)
                else:
                    # .items[0], .labels["name"]
                    assert isinstance(expr.slice, ast.Constant), ast.dump(expr, indent=4)
            else:
                assert isinstance(expr, ast.Attribute), ast.dump(expr, indent=4)
        else:
            assert isinstance(expr, (ast.Attribute, ast.Subscript))
        expr = expr.value
    assert varname is not None, ast.dump(module)
    try:
        value = eval(src, {"__builtins__": {}}, {"obj": obj})
    except (AttributeError, KeyError, IndexError, TypeError) as e:
        if required:
            raise type(e)(f"Failed to traverse {path}: {e}") from e
        return None
    if value is None:
        if required:
            raise TypeError(f"Required {path} is None")
        return value
    if not isinstance(value, get_origin(type_) or type_):
        raise TypeError(f"{path} value is {type(value).__name__}, expected {type_.__name__}")
    return value


def get_cluster_public_ip(api_client: kubernetes_client.CoreV1Api) -> Optional[str]:
    """
    Returns public IP of any cluster node.
    """
    public_ips = get_cluster_public_ips(api_client)
    if len(public_ips) == 0:
        return None
    return public_ips[0]


def get_cluster_public_ips(api_client: kubernetes_client.CoreV1Api) -> List[str]:
    """
    Returns public IPs of all cluster nodes.
    """
    public_ips = []
    for node in api_client.list_node().items:
        addresses = node.status.addresses

        # Look for an external IP address
        for address in addresses:
            if address.type == "ExternalIP":
                public_ips.append(address.address)

    return public_ips
