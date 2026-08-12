import pytest

from dstack._internal.cli.services.presets import prompt as prompt_module
from dstack._internal.cli.services.presets.prompt import get_preset_agent_system_prompt
from dstack._internal.core.errors import CLIError

pytestmark = pytest.mark.windows


class TestSystemPrompt:
    def test_stays_byte_identical_without_user_prompt(self):
        text = get_preset_agent_system_prompt()

        assert text == get_preset_agent_system_prompt(None) == get_preset_agent_system_prompt("")
        assert "## Additional instructions" not in text
        assert "<!--" not in text
        assert "TODO" not in text
        assert "{prompt}" not in text

    def test_injects_user_prompt_with_escape_clause(self):
        text = get_preset_agent_system_prompt("Optimize for RAG traffic.")

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

        assert "directives" in get_preset_agent_system_prompt()
        with pytest.raises(CLIError, match="no place for the user prompt"):
            get_preset_agent_system_prompt("anything")
        # A document that lost the baseline block must fail just as loudly.
        with pytest.raises(CLIError, match="no place for 'baseline'"):
            get_preset_agent_system_prompt(baseline=True)

    def test_drops_maintainer_notes_but_keeps_every_other_comment(self, tmp_path, monkeypatch):
        noted = tmp_path / "system_prompt.md"
        noted.write_text(
            "Kept.\n<!--!TODO: not for the agent.-->\nPlain <!-- comment --> stays.\n"
        )
        monkeypatch.setattr(prompt_module, "_SYSTEM_PROMPT_PATH", noted)

        text = get_preset_agent_system_prompt()

        assert "TODO" not in text
        assert text == "Kept.\nPlain <!-- comment --> stays."

    def test_rejects_unknown_variables_even_in_a_dropped_branch(self, tmp_path, monkeypatch):
        broken = tmp_path / "system_prompt.md"
        broken.write_text("<!--?if previous-->\n<!--?if typo-->\nX\n<!--?end-->\n<!--?end-->\n")
        monkeypatch.setattr(prompt_module, "_SYSTEM_PROMPT_PATH", broken)

        # `previous` is unset, so the branch would be dropped; the typo inside
        # it must not hide behind that.
        with pytest.raises(CLIError, match="Unknown variable"):
            get_preset_agent_system_prompt()

    def test_rejects_malformed_directives(self, tmp_path, monkeypatch):
        broken = tmp_path / "system_prompt.md"
        broken.write_text("Text <!--?typo:oops--> more.\n")
        monkeypatch.setattr(prompt_module, "_SYSTEM_PROMPT_PATH", broken)

        with pytest.raises(CLIError, match="Invalid directive"):
            get_preset_agent_system_prompt()

        broken.write_text("An opener that never closes its comment: <!--?if baseline\n")
        with pytest.raises(CLIError, match="Malformed directive"):
            get_preset_agent_system_prompt()

    def test_inline_blocks_render_in_place(self, tmp_path, monkeypatch):
        doc = tmp_path / "system_prompt.md"
        doc.write_text("A<!--?if baseline-->B<!--?else-->C<!--?end-->D\n")
        monkeypatch.setattr(prompt_module, "_SYSTEM_PROMPT_PATH", doc)

        assert get_preset_agent_system_prompt(baseline=True) == "ABD"
        assert get_preset_agent_system_prompt() == "ACD"

    def test_dedents_only_an_exactly_indented_body(self, tmp_path, monkeypatch):
        doc = tmp_path / "system_prompt.md"
        monkeypatch.setattr(prompt_module, "_SYSTEM_PROMPT_PATH", doc)
        # The reference examples: `baseline` plays <a>, `previous` plays <b>.
        cases = [
            ("<!--?if baseline-->asaga<!--?end-->\n", "asaga"),
            ("<!--?if baseline-->\n  asaga\n<!--?end-->\n", "asaga"),
            (
                "<!--?if baseline-->\n  asaga\n\n  <!--?if previous-->c<!--?end-->\n<!--?end-->\n",
                "asaga\n\nc",
            ),
            (
                "<!--?if baseline-->\n  asaga\n\n"
                "  <!--?if previous-->\n    c\n  <!--?end-->\n<!--?end-->\n",
                "asaga\n\nc",
            ),
            # Not exact: the body keeps its indentation as written.
            (
                "<!--?if baseline-->\nasaga\n\n  <!--?if previous-->c<!--?end-->\n<!--?end-->\n",
                "asaga\n\n  c",
            ),
            # An inline-opened block is never dedented.
            (
                "<!--?if baseline-->asaga\n\n  <!--?if previous-->c<!--?end-->\n<!--?end-->\n",
                "asaga\n\n  c",
            ),
        ]
        for content, expected in cases:
            doc.write_text(content)
            previous = "x" if "previous" in content else None
            rendered = get_preset_agent_system_prompt(baseline=True, previous=previous)
            assert rendered.strip("\n") == expected, content

    def test_nested_blocks_render_one_branch(self, tmp_path, monkeypatch):
        nested = tmp_path / "system_prompt.md"
        nested.write_text(
            "<!--?if previous-->\n"
            "  IDS={previous}\n"
            "\n"
            "  <!--?if baseline-->\n"
            "    SEEDED\n"
            "  <!--?end-->\n"
            "<!--?else-->\n"
            "  <!--?if baseline-->\n"
            "    SOLO\n"
            "  <!--?end-->\n"
            "<!--?end-->\n"
        )
        monkeypatch.setattr(prompt_module, "_SYSTEM_PROMPT_PATH", nested)

        assert get_preset_agent_system_prompt().strip() == ""
        assert get_preset_agent_system_prompt(baseline=True).strip() == "SOLO"
        assert get_preset_agent_system_prompt(previous="a1, b2").strip() == "IDS=a1, b2"
        both = get_preset_agent_system_prompt(baseline=True, previous="a1")
        assert both.strip() == "IDS=a1\n\nSEEDED"

    def test_unbalanced_blocks_fail_loudly(self, tmp_path, monkeypatch):
        for content, error in [
            ("<!--?if baseline-->\nnever closed\n", "Unclosed"),
            ("text\n<!--?end-->\n", "`end` without"),
            ("text\n<!--?else-->\n", "`else` without"),
            ("<!--?if baseline-->\n<!--?else-->\n<!--?else-->\n<!--?end-->\n", "`else` without"),
        ]:
            broken = tmp_path / "system_prompt.md"
            broken.write_text(content)
            monkeypatch.setattr(prompt_module, "_SYSTEM_PROMPT_PATH", broken)
            with pytest.raises(CLIError, match=error):
                get_preset_agent_system_prompt()
