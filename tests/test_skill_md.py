import re
from pathlib import Path

SKILL_MD = Path(__file__).parent.parent / "skills" / "wiki-interest-trends" / "SKILL.md"


def _frontmatter_and_body():
    text = SKILL_MD.read_text()
    assert text.startswith("---\n"), "SKILL.md must start with YAML frontmatter"
    _, frontmatter, body = text.split("---", 2)
    fields = {}
    for line in frontmatter.strip().splitlines():
        if line.startswith(" ") or ":" not in line:
            continue
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    return fields, body


def test_name_matches_agent_skills_spec_and_directory_name():
    fields, _ = _frontmatter_and_body()
    name = fields["name"]

    assert 1 <= len(name) <= 64
    assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", name), name
    assert name == SKILL_MD.parent.name


def test_description_within_length_and_has_no_angle_brackets():
    text = SKILL_MD.read_text()
    _, frontmatter, _ = text.split("---", 2)
    m = re.search(r"^description:\s*(.+)$", frontmatter, re.MULTILINE)
    assert m, "description field not found"
    description = m.group(1)

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
