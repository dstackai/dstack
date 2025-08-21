def add_extra_schema_types(schema_property: dict, extra_types: list[dict]):
    if "allOf" in schema_property:
        refs = [schema_property.pop("allOf")[0]]
    elif "anyOf" in schema_property:
        refs = schema_property.pop("anyOf")
    elif "type" in schema_property:
        refs = [{"type": schema_property.pop("type")}]
    else:
        refs = [{"$ref": schema_property.pop("$ref")}]
    refs.extend(extra_types)
    schema_property["anyOf"] = refs
