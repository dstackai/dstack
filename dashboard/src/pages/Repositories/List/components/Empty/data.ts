export const installCliCode = `@requires_authorization
def somefunc(param1='', param2=0):
    r'''A docstring'''
    if param1 > param2: # interesting
        print 'Gre\\'ater'
    return (param2 - param1 + 1 + 0b10l) or None

class SomeClass:
    pass

>>> message = '''interpreter
... prompt'''
`;

export const cloneCode = `@requires_authorization
def somefunc(param1='', param2=0):
`;

export const runWorkflow = `@requires_authorization
def somefunc(param1='', param2=0):
`;
