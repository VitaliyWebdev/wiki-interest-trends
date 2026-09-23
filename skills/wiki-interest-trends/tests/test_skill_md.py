import re
from pathlib import Path

from skills_ref import validate as skills_ref_validate
from skills_ref.parser import parse_frontmatter

SKILL_DIR = Path(__file__).parent.parent
SKILL_MD = SKILL_DIR / "SKILL.md"


def _frontmatter_and_body():
    # Real YAML parsing, not hand-rolled line-splitting -- a naive
    # per-line `key: value` split previously read a `description` value
    # just fine even though it was invalid YAML (a bare "word: word"
    # inside an unquoted plain scalar). skills-ref uses the same strict
    # parser the reference validator below runs, so a test built on it
    # can't pass on frontmatter the spec's own tooling would reject.
    text = SKILL_MD.read_text(encoding="utf-8")
    return parse_frontmatter(text)


def test_passes_the_official_agent_skills_reference_validator():
    # The authoritative check: the same `skills-ref` validator the spec
    # itself points to (agentskills.io/specification#validation). Real
    # incident this caught: our `description` field was invalid YAML
    # (an unquoted "word: word" sequence broke strict parsing) despite
    # every hand-written check below passing, because those checks never
    # actually ran a YAML parser over the file.
    errors = skills_ref_validate(SKILL_DIR)
    assert errors == [], errors


def test_name_matches_agent_skills_spec_and_directory_name():
    fields, _ = _frontmatter_and_body()
    name = fields["name"]

    assert 1 <= len(name) <= 64
    assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", name), name
    assert name == SKILL_MD.parent.name


def test_description_within_length_and_has_no_angle_brackets():
    fields, _ = _frontmatter_and_body()
    description = fields["description"]

    assert 1 <= len(description) <= 1024
    assert "<" not in description
    assert ">" not in description


def test_compatibility_present_and_within_length():
    fields, _ = _frontmatter_and_body()

    assert "compatibility" in fields
    assert 1 <= len(fields["compatibility"]) <= 500


def test_body_under_recommended_line_count():
    _, body = _frontmatter_and_body()

    line_count = len(body.strip("\n").splitlines())
    assert line_count < 300, f"SKILL.md body is {line_count} lines, spec target is ~300"


def test_referenced_files_exist():
    _, body = _frontmatter_and_body()
    root = SKILL_MD.parent

    for m in re.finditer(r"\((references/[\w.\-/]+\.md)\)", body):
        referenced = root / m.group(1)
        assert referenced.exists(), f"SKILL.md links to {m.group(1)} but it doesn't exist"


def test_scripts_referenced_in_skill_md_exist():
    _, body = _frontmatter_and_body()
    root = SKILL_MD.parent

    for script_name in ("resolve_topic.py", "analyze.py", "report.py"):
        assert f"scripts/{script_name}" in body
        assert (root / "scripts" / script_name).exists()


def test_body_tells_agent_to_reattempt_instead_of_trusting_a_stale_network_conclusion():
    # Real incident: an agent recalled an earlier network failure from
    # earlier in the same conversation and told the user "this
    # environment has no access" without ever re-running the command in
    # that attempt -- skipping straight to a manual workaround the skill
    # exists to avoid. No script-side fix can catch this, since the
    # script was never even called; this has to be a workflow rule.
    _, body = _frontmatter_and_body()

    assert "without actually" in body.lower() or "re-attempt" in body.lower()
    assert "earlier" in body.lower() and "conversation" in body.lower()
