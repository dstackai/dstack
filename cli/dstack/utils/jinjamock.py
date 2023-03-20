class JinjaMockValue:
    def __init__(self, s: str):
        self.__s__ = s

    def __repr__(self):
        return self.__s__

    def __getattr__(self, item):
        raise ValueError()

    def __getitem__(self, item):
        raise ValueError()


class JinjaMock:
    """
    Example:
        value = "${{ secrets.any_key }}"
        assert value == Template(value, variable_start_string="${{").render(secrets=JinjaMock("secrets"))
    """

    def __init__(self, namespace: str):
        self.__n__ = namespace

    def __getattr__(self, item: str) -> JinjaMockValue:
        namespace = self.__dict__["__n__"]
        return JinjaMockValue(" ".join(["${{", f"{namespace}.{item}", "}}"]))
