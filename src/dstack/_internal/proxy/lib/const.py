"""
Shared constants for proxy components (gateway + in-server proxy).
"""

# Inference endpoints exposed by the in-replica HTTP router. Applies to both
# SGLang's router and Dynamo's `dynamo.frontend` — they share the
# OpenAI-compatible endpoint surface.
ROUTER_WHITELISTED_PATHS: tuple[str, ...] = (
    "/generate",
    "/v1/",
    "/chat/completions",
)
