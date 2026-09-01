"""
Shared constants for proxy components (gateway + in-server proxy).
"""

DEFAULT_PROXY_READ_TIMEOUT = 300
"""Default maximum interval between reads from a service upstream, in seconds."""

# Inference endpoints exposed by the in-replica HTTP router. Applies to both
# SGLang's router and Dynamo's `dynamo.frontend` — they share the
# OpenAI-compatible endpoint surface.
ROUTER_WHITELISTED_PATHS: tuple[str, ...] = (
    "/generate",
    "/v1/",
    "/chat/completions",
)
