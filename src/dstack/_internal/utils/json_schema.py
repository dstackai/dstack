def add_extra_schema_types(schema_property: dict, extra_types: list[dict]):
    if "allOf" in schema_property:
        ref = schema_property.pop("allOf")[0]
    else:
        ref = {"type": schema_property.pop("type")}
    schema_property["anyOf"] = [ref, *extra_types]
