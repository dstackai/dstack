workflows_schema_yaml = """type: object
additionalProperties: false
properties:
  workflows:
    type: array
    items:
      oneOf:
        - $ref: '#/components/schemas/workflow-no-provider'
        - $ref: '#/components/schemas/workflow-provider'
required:
  - workflows
components:
  schemas:
    workflow-no-provider:
      type: object
      properties:
        name:
          type: string
          minLength: 1
        image:
          type: string
          minLength: 1
        commands:
          type: array
          items:
            type: string
            minLength: 1
          minItems: 1
        artifacts:
          type: array
          items:
            type: string
            minLength: 1
          minItems: 1
        resources:
          oneOf:
            - $ref: '#/components/schemas/resources'
        depends-on:
          oneOf:
            - $ref: '#/components/schemas/depends-on-object'
            - $ref: '#/components/schemas/depends-on-array'
      additionalProperties: false
      required:
        - name
        - image
        - commands
    workflow-provider:
      type: object
      properties:
        name:
          type: string
          minLength: 1
        depends-on:
          oneOf:
            - $ref: '#/components/schemas/depends-on-object'
            - $ref: '#/components/schemas/depends-on-array'
      additionalProperties: true
      required:
        - name
        - provider
    depends-on-object:
      type: object
      additionalProperties: false
      properties:
        repo:
          type: object
          additionalProperties: false
          properties:
            include:
              type: array
              items:
                type: string
                minLength: 1
              minItems: 1
        workflows:
          type: array
          items:
            type: string
            minLength: 1
          minItems: 1
    depends-on-array:
      type: array
      items:
        type: string
        minLength: 1
      minItems: 1
    resources:
      type: object
      additionalProperties: false
      properties:
        cpu:
          oneOf:
          - $ref: '#/components/schemas/cpu-count'
          - $ref: '#/components/schemas/cpu'
        memory:
          type: string
          minLength: 1
        gpu:    
          oneOf:      
            - $ref: '#/components/schemas/gpu-count'
            - $ref: '#/components/schemas/gpu'
      patternProperties:
        ".+/gpu":
          oneOf:
            - $ref: '#/components/schemas/gpu'
    cpu-count:
      type: object
      additionalProperties: false
      properties:
        count:
          type: integer
          minimum: 1
      required:
        - count
    cpu:
      type: integer
      minimum: 1
    gpu-count:
      type: object
      additionalProperties: false
      properties:
        count:
          type: integer
          minimum: 1
        name:
          type: string
          minLength: 1
        memory:
          type: string
          minLength: 1
    gpu:
      type: integer
      minimum: 1
      """