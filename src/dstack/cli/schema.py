workflows_schema_yaml = """type: object
additionalProperties: false
properties:
  workflows:
    type: array
    items:
      type: object
      properties:
        name:
          type: string
          minLength: 1
        help:
          type: string
          minLength: 1
        depends-on:
          type: array
          items:
            type: string
            minLength: 1
          minItems: 1
      additionalProperties: true
      required:
        - name
        - provider
required:
  - workflows
"""