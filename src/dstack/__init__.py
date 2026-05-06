import sys

if sys.version_info >= (3, 14):
    raise ImportError("dstack does not support Python 3.14 or later. Please use Python 3.10–3.13.")
