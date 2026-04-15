"""
Shared constants for proxy components (gateway + in-server proxy).
"""

SGLANG_WHITELISTED_PATHS: tuple[str, ...] = (
    "/generate",
    "/v1/",
    "/chat/completions",
)
