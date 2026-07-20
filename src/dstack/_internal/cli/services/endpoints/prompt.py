from pathlib import Path

_SYSTEM_PROMPT_PATH = Path(__file__).resolve().parent / "resources" / "system_prompt.md"


# TODO: reintroduce a `# Resume` section in system_prompt.md once session resume
# (seeded from `runs.jsonl` and `trials.jsonl`) is designed.
def get_endpoint_agent_system_prompt() -> str:
    return _SYSTEM_PROMPT_PATH.read_text(encoding="utf-8").strip()
