def add_extra_schema_types(schema_property: dict, extra_types: list[dict]):
    if "allOf" in schema_property:
        refs = [schema_property.pop("allOf")[0]]
    elif "anyOf" in schema_property:
        refs = schema_property.pop("anyOf")
    else:
        refs = [{"type": schema_property.pop("type")}]
    refs.extend(extra_types)
    schema_property["anyOf"] = refs
