"""The blank bible the API seeds is the yaml template the CLI seeds — same keys.

`backend/studio_core/profile_template.json` is `templates/profile.yaml` with
the placeholders emptied, so a character made in the app and one made by
`studio character create` start from the same form. Two files, one shape —
and nothing but this test says so. A field added to one and not the other is
a character that starts differently depending on which door it came in by.

Keys only: the yaml's values are placeholders and the json's are blank, and a
list of maps is compared by its first entry, which is the one the json keeps.
"""

import json

import pytest
import yaml

from studio_pipeline import STUDIO_DIR

TEMPLATES = STUDIO_DIR / "pipeline" / "src" / "studio_pipeline" / "domain" / "templates"
BACKEND = STUDIO_DIR / "backend" / "studio_core"

#: One pair per subject kind. A location's bible is seeded the same two ways a
#: character's is, so the same contract holds it.
PAIRS = {
    "character": (TEMPLATES / "profile.yaml", BACKEND / "profile_template.json"),
    "location": (TEMPLATES / "location.yaml", BACKEND / "location_template.json"),
}


def _shape(value):
    """The key tree, with every scalar and every empty list folded to `None`."""
    if isinstance(value, dict):
        return {key: _shape(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_shape(value[0])] if value and isinstance(value[0], dict) else []
    return None


@pytest.mark.parametrize("kind", sorted(PAIRS))
def test_the_api_blank_bible_has_the_yaml_template_keys(kind):
    yaml_path, json_path = PAIRS[kind]
    authored = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    authored.pop("name")  # promoted to the record; not part of `profile`
    seeded = json.loads(json_path.read_text(encoding="utf-8"))["profile"]
    assert _shape(seeded) == _shape(authored)


@pytest.mark.parametrize("kind", sorted(PAIRS))
def test_every_leaf_the_yaml_explains_has_a_hint(kind):
    """A `<placeholder>` in the yaml is a hint in the json, keyed without indexes."""
    yaml_path, json_path = PAIRS[kind]
    hints = json.loads(json_path.read_text(encoding="utf-8"))["hints"]
    authored = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))

    def walk(value, path):
        if isinstance(value, dict):
            for key, child in value.items():
                yield from walk(child, [*path, key])
        elif isinstance(value, list) and value:
            yield from walk(value[0], path)
        elif isinstance(value, str) and value.strip().startswith("<"):
            yield ".".join(path)

    explained = {path for path in walk(authored, []) if path != "name"}
    assert explained <= set(hints), sorted(explained - set(hints))
