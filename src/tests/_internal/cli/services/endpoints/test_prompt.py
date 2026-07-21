import pytest

from dstack._internal.cli.services.endpoints import prompt as prompt_module
from dstack._internal.cli.services.endpoints.prompt import get_endpoint_agent_system_prompt
from dstack._internal.core.errors import CLIError

pytestmark = pytest.mark.windows


class TestSystemPrompt:
    def test_stays_byte_identical_without_user_prompt(self):
        text = get_endpoint_agent_system_prompt()

        assert (
            text == get_endpoint_agent_system_prompt(None) == get_endpoint_agent_system_prompt("")
        )
        assert "## Additional instructions" not in text
        assert "<!--?" not in text
        assert "{prompt}" not in text

    def test_injects_user_prompt_with_escape_clause(self):
        text = get_endpoint_agent_system_prompt("Optimize for RAG traffic.")

        clause_at = text.index("unless `## Additional instructions` explicitly allows it.")
        section_at = text.index(
            "## Additional instructions\n\n```\nOptimize for RAG traffic.\n```"
        )
        assert clause_at < section_at < text.index("## CLI And Skills")
        assert "<!--?" not in text

    def test_fails_loudly_when_the_prompt_has_no_directives(self, tmp_path, monkeypatch):
        plain = tmp_path / "system_prompt.md"
        plain.write_text("# Objective\n\nA prompt without directives.\n")
        monkeypatch.setattr(prompt_module, "_SYSTEM_PROMPT_PATH", plain)

        assert "directives" in get_endpoint_agent_system_prompt()
        with pytest.raises(CLIError, match="no place for the user prompt"):
            get_endpoint_agent_system_prompt("anything")

    def test_rejects_unknown_directive_variables(self, tmp_path, monkeypatch):
        broken = tmp_path / "system_prompt.md"
        broken.write_text("Text <!--?typo:oops--> more.\n")
        monkeypatch.setattr(prompt_module, "_SYSTEM_PROMPT_PATH", broken)

        with pytest.raises(CLIError, match="Unknown variable"):
            get_endpoint_agent_system_prompt()
