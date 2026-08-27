"""`studio phrasebook` — per-model wording lists, now `TERM#` rows.

**Half of what this file used to test no longer exists to be tested.** It was a
YAML document reached by raw S3 key, so the suite guarded the document: that a
missing one read as empty rather than raising, that the empty document was not
shared between reads (a module-level `{"models": {}}` collected the first
`add`'s section and handed it to the next reader), that the read went through
the key-addressed route and never tried to resolve a node, and that a 403 was
not mistaken for "no phrasebook".

Every one of those was a property of having a document. There is no document.
What replaced them is the property the rows give and the document could not:
uniqueness is a key, so a duplicate pair is refused rather than appended beside
the first — and `add` on a library that has never held a phrasebook simply
works, which is the failure the whole arrangement existed to work around.

The one guard that survives unchanged is the empty-`avoid` skip, because `""` is
a substring of everything and a wording list that refuses every draft is worse
than no wording list.
"""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from studio_pipeline import cli
from studio_pipeline.adapters import api, entities as E
from studio_pipeline.domain import phrasebook as PB

MODEL = "kling"


def _run(*args):
    return CliRunner().invoke(cli.main, ["phrasebook", *args])


# ── reading ─────────────────────────────────────────────────────────────────

def test_a_library_with_no_terms_reads_as_empty_rather_than_failing(library):
    """A model with no wording list is an ordinary state, not an error.

    This survives from the document era for the same reason it held then: every
    caller asks "what should I avoid here" and none distinguishes absent from
    empty. What changed is that it is now true by construction — there is no
    read that can 404.
    """
    assert PB.terms(MODEL) == []
    assert E.phrasebook() == []


def test_terms_carry_only_what_a_caller_reads(library):
    """`domain/prompt.py` and the engine read exactly `avoid` and `use`.

    Pinned because the row carries more — `note`, `replicate`, `added` — and a
    helper that leaked them would make every caller filter, or worse, not.
    """
    E.add_phrasebook_term(MODEL, "a phrase", "another phrase",
                          note="from a refusal", replicate="kwaivgi/kling")
    assert PB.terms(MODEL) == [{"avoid": "a phrase", "use": "another phrase"}]


def test_terms_are_scoped_to_one_model(library):
    """Different models read the same idea differently — that is the point."""
    E.add_phrasebook_term(MODEL, "a phrase", "for kling")
    E.add_phrasebook_term("seedance", "a phrase", "for seedance")
    assert PB.terms(MODEL) == [{"avoid": "a phrase", "use": "for kling"}]
    assert PB.terms("seedance") == [{"avoid": "a phrase", "use": "for seedance"}]


def test_show_groups_by_model_in_the_shape_the_document_had(library):
    """`replicate` plus `entries`, because that is what every `SKILL.md` shows.

    The storage changed; the reading did not. A person who learned this output
    from the YAML file should not have to relearn it.
    """
    E.add_phrasebook_term(MODEL, "a phrase", "another phrase",
                          replicate="kwaivgi/kling")
    result = _run("show")
    assert result.exit_code == 0, result.output
    assert "kwaivgi/kling" in result.output
    assert "entries:" in result.output
    assert "a phrase" in result.output


def test_show_for_a_model_with_nothing_recorded_says_so(library):
    result = _run("show", "--model", "seedance")
    assert result.exit_code == 1
    assert "no phrasebook section" in result.output


def test_models_lists_what_is_covered(library):
    E.add_phrasebook_term(MODEL, "a phrase", "another phrase",
                          replicate="kwaivgi/kling")
    result = _run("models")
    assert result.exit_code == 0, result.output
    assert MODEL in result.output
    assert "entries=1" in result.output


# ── checking a draft ────────────────────────────────────────────────────────

def test_check_exits_one_on_a_hit_and_says_what_to_use_instead(library):
    E.add_phrasebook_term(MODEL, "a phrase", "another phrase", note="why")
    result = _run("check", "--model", MODEL, "--text", "it opens on A PHRASE here")
    assert result.exit_code == 1
    assert "AVOID" in result.output and "another phrase" in result.output
    assert "why" in result.output


def test_check_passes_a_draft_nothing_matches(library):
    E.add_phrasebook_term(MODEL, "a phrase", "another phrase")
    result = _run("check", "--model", MODEL, "--text", "nothing matches")
    assert result.exit_code == 0
    assert "no substitutions apply (1 entries)" in result.output


def test_check_against_a_model_with_no_list_is_not_a_failure(library):
    result = _run("check", "--model", "seedance", "--text", "anything")
    assert result.exit_code == 0
    assert "no wording list" in result.output


def test_an_empty_avoid_is_skipped_rather_than_matching_everything(library, monkeypatch):
    """**`""` is a substring of every string.**

    The one guard that survives the move unchanged. A row with an empty `avoid`
    should not exist — the CLI requires the option — but a hand-written row or a
    migrated placeholder can produce one, and a wording list that refuses every
    draft it is shown is worse than no wording list at all.
    """
    monkeypatch.setattr(E, "phrasebook",
                        lambda model=None: [{"model": MODEL, "avoid": "",
                                             "use": "something"}])
    result = _run("check", "--model", MODEL, "--text", "an innocent draft")
    assert result.exit_code == 0
    assert "no substitutions apply" in result.output


# ── writing ─────────────────────────────────────────────────────────────────

def test_add_works_on_a_library_that_has_never_held_a_phrasebook(library):
    """**The failure that disappeared, and the reason the rows exist.**

    `add` wrote through `PATCH /api/text`, a route that overwrites an existing
    key and cannot invent one — studio's API has no upload, and this was the one
    write in it a person authors. So the FIRST entry anybody tried to record in
    a fresh library was refused, and the workaround was a seed copy in the repo
    plus a line in `dev-setup.sh` that pushed it only when the key was absent
    (#425), carefully, because from the first `add` the bucket's copy was the
    live document and a plain sync would have deleted its entries.

    A row has no precondition. This library has never held a phrasebook.
    """
    result = _run("add", "--model", MODEL, "--avoid", "a phrase",
                  "--use", "another phrase")
    assert result.exit_code == 0, result.output
    assert PB.terms(MODEL) == [{"avoid": "a phrase", "use": "another phrase"}]


def test_a_duplicate_pair_is_refused_rather_than_appended(library):
    """**New, and it is uniqueness the document could not enforce.**

    A YAML list happily held the same `avoid` twice with different replacements,
    and `check` then printed whichever came first. The pair is part of the sort
    key now, so the second write is a 409.
    """
    _run("add", "--model", MODEL, "--avoid", "a phrase", "--use", "another phrase")
    result = _run("add", "--model", MODEL, "--avoid", "a phrase", "--use", "a third")
    assert result.exit_code == 1
    assert "already records" in result.output
    assert PB.terms(MODEL) == [{"avoid": "a phrase", "use": "another phrase"}]


def test_the_same_phrase_may_be_recorded_for_two_models(library):
    """The model is in the key too, so the two do not collide."""
    assert _run("add", "--model", MODEL, "--avoid", "a phrase",
                "--use", "for kling").exit_code == 0
    assert _run("add", "--model", "seedance", "--avoid", "a phrase",
                "--use", "for seedance").exit_code == 0


def test_rm_removes_one_entry(library):
    """**New — removing one entry from a document meant rewriting the whole
    document, so nothing offered it.**"""
    _run("add", "--model", MODEL, "--avoid", "a phrase", "--use", "another phrase")
    result = _run("rm", "--model", MODEL, "--avoid", "a phrase")
    assert result.exit_code == 0, result.output
    assert PB.terms(MODEL) == []


def test_rm_of_something_that_is_not_there_says_where_to_look(library):
    result = _run("rm", "--model", MODEL, "--avoid", "a phrase")
    assert result.exit_code == 1
    assert "records no substitution" in result.output


def test_a_model_key_with_a_slash_survives_the_round_trip(library):
    """Both path segments are quoted, and the model key is the one that needs it.

    `google/nano-banana-pro` would otherwise split into two path segments and
    404 on delete — which is why `delete_phrasebook_term` passes `safe=''`
    rather than taking `quote`'s default, which keeps `/`.
    """
    model = "google/nano-banana-pro"
    assert _run("add", "--model", model, "--avoid", "a phrase",
                "--use", "another phrase").exit_code == 0
    assert _run("rm", "--model", model, "--avoid", "a phrase").exit_code == 0
    assert E.phrasebook(model=model) == []


def test_a_refusal_is_left_to_surface(library, monkeypatch):
    """A 403 is a different fact from "no phrasebook", and always was.

    The document version caught every exception and grepped the message for
    `NoSuchKey`, so a permission failure read as an absent file and the
    phrasebook reported "no substitutions apply" for a draft it never checked.
    Nothing here catches broadly, and this pins that.
    """
    def _forbidden(**_kwargs):
        raise api.Forbidden("not a member of this library", 403)

    monkeypatch.setattr(E, "phrasebook", _forbidden)
    with pytest.raises(api.Forbidden):
        PB.terms(MODEL)
