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
        deps:
          type: array
          items:
            oneOf:
              - type: string
                minLength: 1
              - type: object
                properties:
                  tag: 
                    type: string
                    minLength: 1
                  mount:
                    type: boolean
                required:
                  - tag                  
              - type: object
                properties:
                  workflow: 
                    type: string
                    minLength: 1
                  mount:
                    type: boolean
                required:
                  - workflow                  
          minItems: 1
      additionalProperties: true
      required:
        - name
        - provider
required:
  - workflows
"""