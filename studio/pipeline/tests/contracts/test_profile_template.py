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

import yaml

from studio_pipeline import STUDIO_DIR

YAML = STUDIO_DIR / "pipeline" / "src" / "studio_pipeline" / "domain" / "templates" / "profile.yaml"
JSON = STUDIO_DIR / "backend" / "studio_core" / "profile_template.json"


def _shape(value):
    """The key tree, with every scalar and every empty list folded to `None`."""
    if isinstance(value, dict):
        return {key: _shape(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_shape(value[0])] if value and isinstance(value[0], dict) else []
    return None


def test_the_api_blank_bible_has_the_yaml_template_keys():
    authored = yaml.safe_load(YAML.read_text(encoding="utf-8"))
    authored.pop("name")  # promoted to the record; not part of `profile`
    seeded = json.loads(JSON.read_text(encoding="utf-8"))["profile"]
    assert _shape(seeded) == _shape(authored)


def test_every_leaf_the_yaml_explains_has_a_hint():
    """A `<placeholder>` in the yaml is a hint in the json, keyed without indexes."""
    hints = json.loads(JSON.read_text(encoding="utf-8"))["hints"]
    authored = yaml.safe_load(YAML.read_text(encoding="utf-8"))

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
