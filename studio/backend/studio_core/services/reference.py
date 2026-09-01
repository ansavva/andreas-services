"""Fill a reference angle's template from a character's bible.

**The half of a turnaround that decides what a reference render SAYS.** It lived
in `engine/turnaround.py` in the pipeline package, which put it behind a
`pip install`: the SPA could not assemble a reference prompt, so it could not
show one, preview one or make one. Everything else a turnaround needs — the
character record, the reference index, the run rows — the API already served.

Moved rather than copied. A second implementation of this on the SPA side would
be two opinions about what a run was told to render, and the disagreement would
be invisible after the fact because the run records the outcome and not the
reasoning. That is the argument `engine/refs.py` records for moving selection to
`GET /api/characters/<id>/selection`, and it holds here unchanged.

## What a template may cite

Blocks by name, and these computed values:

    {character.top}            the character's usual garment, plainly
    {character.style}          the MEDIUM to render in — the character's, never ours
    {character.must}           the consistency checklist, introduced by the group's intro
    {character.build}          proportions, from the bible, group-dependent
    {character.age}            `identity.apparent_age`
    {character.identity_block} the authored ~50-70 word compression, if any
    {slot.identity}            `[Image1], [Image2] and [Image3]` — where the
                               identity images actually landed
    {slot.anchor}              the `anchor` block, when this shoot is chained off
                               an earlier render, and "" when it is not

**There are no plate slots, and there is no plate.** An angle used to be able to
bind a generic pose figure from `config/` as a first image, cited as
`{angle_slot}`, with a `guide` block spending a paragraph telling the model to
take the stance from it and nothing else. It distorted the very thing it was
there to record — the face angles stopped sending theirs first, and the body
angles followed once eleven hand-authored production renders were compared and
not one of them had bound a plate. The mechanism is gone rather than disabled:
left in place it was a loaded gun with an authored block still arguing for it.
"""

import string
from types import SimpleNamespace

from studio_core.errors import ValidationError

#: Read only on a BODY angle. A face angle crops at mid-chest, so anything below
#: the crop is noise in its prompt.
BELOW_THE_CROP = frozenset({"midsection", "lower_body", "lower_body_and_hands",
                            "body_hair", "feet"})

#: Not a description of the build — a rendering direction already carried by its
#: own clause. Sweeping it in would say it twice.
NOT_BUILD = frozenset({"posture"})

#: The body fields whose ORDER matters, in that order. Anything else the bible
#: carries is swept up after them by `_extra_body_fields`, so a newly written
#: field reaches the prompt without an edit here — a missing field is the one
#: failure mode that leaves no trace in the payload.
BODY_FIELDS = ("silhouette", "chest_and_shoulders", "back", "neck", "arms", "hands")
BODY_ONLY_FIELDS = ("midsection", "lower_body", "lower_body_and_hands", "body_hair")


def _clean(value) -> str:
    """One bible FIELD, flattened to a line.

    Deliberately still collapsing, and deliberately not what happens to the
    assembled prompt. A bible field is a sentence or two stored in a form; the
    line breaks in it are the textarea's, not the author's. The TEMPLATE is the
    opposite case and keeps every one — see `assemble`.
    """
    return " ".join(str(value or "").split())


def top_text(profile: dict) -> str:
    """The garment an angle should wear: the most frequent top, plainly.

    The bible's first `tops[]` entry is the usual one, and its `detail` often
    names embroidery or a graphic — which a model renders differently every time
    and would make the group inconsistent. So the detail is not used.

    The schema puts the COLOUR in that same field, though, so dropping it whole
    threw the colour away too and an angle came back in a colour nobody chose.
    `colour:` is the narrow way back in.
    """
    tops = ((profile.get("wardrobe") or {}).get("tops")) or []
    top = tops[0] if tops and isinstance(tops[0], dict) else {}
    item = (top.get("item") or "plain T-shirt").strip().rstrip(".").lower()
    colour = str(top.get("colour") or "").strip().rstrip(".").lower()
    return (f"Wearing a plain {colour + ' ' if colour else ''}{item}, unbranded, "
            f"with no logo, text or embroidery")


def style_text(profile: dict, blocks: dict) -> str:
    """What MEDIUM to render in — the character's, never this code's.

    The spec used to assert "photographic, no stylisation" for every angle, which
    is right only for a character whose material is photographs. For one who
    exists as pen-and-ink panels it would convert him to a medium he has never
    appeared in, with the reference images fighting the prompt.
    """
    style = ((profile.get("rendering") or {}).get("default_style") or "").strip()
    intro = (blocks.get("style_intro") or "").strip()
    fallback = blocks.get("style_fallback", "")
    return f"{intro} {style.rstrip('.') or fallback}.".strip()


def must_text(profile: dict, intro: str) -> str:
    musts = ((profile.get("consistency") or {}).get("must")) or []
    if not musts:
        return ""
    return intro.strip() + " " + "; ".join(m.strip().rstrip(".") for m in musts) + "."


def age_text(profile: dict) -> str:
    """`identity.apparent_age`.

    Seed photographs accumulate over years — the same person at 35 and at 55 in
    one identity set, with the model free to average them. Nothing in the prompt
    named an age, so nothing decided it.
    """
    return _clean((profile.get("identity") or {}).get("apparent_age"))


def _extra_body_fields(body: dict, already: tuple) -> tuple:
    """Body fields the named tuples miss, in the bible's own order."""
    seen = set(already) | NOT_BUILD
    below = BELOW_THE_CROP & set(already)
    return tuple(k for k in body
                 if k not in seen and (below or k not in BELOW_THE_CROP))


def _label(field: str) -> str:
    """`chest_and_shoulders` -> `Chest and shoulders`."""
    return field.replace("_", " ").capitalize()


def build_text(profile: dict, group: str = "body") -> str:
    """The person's PROPORTIONS — from the bible, never from here.

    HEIGHT comes first, and from `identity` rather than `body`: it is the one
    proportion the bible states as a NUMBER, and a figure on a plain backdrop
    has no scale of its own, so the number is the only thing that settles it. It
    was the only field never sent, because the build clause read `body:` alone.

    ## One LABELLED line per field, and that is the change

    This joined every field with a space into one run-on paragraph, and the
    hand-authored body prompts that actually worked did not: they arrived as

        - Chest: Full square chest, rounded capped deltoids... SEEN FROM THE
          SIDE the chest has real DEPTH...
        - Legs: ...
        - Body hair: ...

    with each field named and on its own line. Which field a sentence belongs to
    is information the bible has and the run-on form threw away — and it is the
    information a turned body angle needs most, because "the chest curves out in
    side view" only reads as an instruction about the chest if it is labelled as
    one. A wall of unattributed sentences is what produced a flat side profile
    from a good front one.

    The label is the bible's own key, so a field written into the bible tomorrow
    is labelled without an edit here.
    """
    body = profile.get("body") or {}
    fields = BODY_FIELDS
    if group != "face":
        fields += BODY_ONLY_FIELDS
    fields += _extra_body_fields(body, fields)

    lines = []
    height = _clean((profile.get("identity") or {}).get("height_read"))
    if height:
        lines.append(f"- Height: {height}")
    for field in fields:
        value = _clean(body.get(field))
        if value:
            lines.append(f"- {_label(field)}: {value}")
    return "\n".join(lines)


def slots_phrase(positions: list) -> str:
    """[Image2] / [Image2] and [Image3] / [Image2], [Image3] and [Image4]."""
    names = [f"[Image{n}]" for n in positions]
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + " and " + names[-1]


#: The three namespaces a template may address, and what each one is edited on.
#: Named here so a refusal can say where to go rather than only what is wrong.
NAMESPACES = {"block": "the Blocks tab",
              "character": "the character's Profile tab",
              "slot": "the photographs picked for this angle"}

#: The bare names the assembler computes. Kept for the LEGACY spelling only —
#: `{character.top}` is the form to write — and the set a bare name is checked
#: against when a block claims the same word.
COMPUTED = frozenset({"top", "style", "must", "build", "age", "identity_block",
                      "identity_slots"})


def _bare_names(template: str) -> set:
    """Every `{name}` a template cites WITHOUT a namespace.

    A malformed template comes back as no names rather than as an exception:
    parsing it is how `vformat` finds a stray brace too, and this runs first, so
    raising here would replace the refusal that explains doubling a brace with a
    bare `ValueError`.
    """
    found = set()
    try:
        fields = list(string.Formatter().parse(template or ""))
    except ValueError:
        return found
    for _literal, field, _spec, _conv in fields:
        if field and "." not in field:
            found.add(field)
    return found


def values_for(angle: dict, blocks: dict, profile: dict,
               identity_positions=None, anchored: bool = False) -> dict:
    """Everything a template may cite, computed once.

    **Two spellings of the same values, and the dotted one is the point.**
    `{block.scale_face}` and `{character.top}` say where a placeholder comes
    from, which is the question a reader of an assembled prompt actually has —
    and, more than that, they cannot collide. Bare names share one flat
    namespace, so a block called `top` was silently beaten by the bible's
    `top_text`, and a block called `angle_slot` won or lost depending on whether
    the angle happened to bind a plate. Neither said anything.

    A dot in a format field is ATTRIBUTE access rather than a nested key, so
    each namespace goes in as an object. Every block name matches
    `[a-z_][a-z0-9_]*`, which is also the rule for a Python identifier, so all
    of them are reachable this way.

    The bare spelling is kept and resolves exactly as it did, because every
    template written so far uses it and the assembled OUTPUT is identical either
    way — `plan_digest` hashes the prompt, not the template, so moving a
    template over stales no approval. `assemble` refuses only the bare names
    that are genuinely ambiguous.
    """
    group = angle.get("group") or "face"

    block_ns = {k: v for k, v in blocks.items() if isinstance(v, str)}
    character_ns = character_values(profile, blocks, group)
    # **The anchor's sentence, or nothing at all.**
    #
    # A turnaround is not fourteen independent renders. Every hand-authored
    # production set was shot as one ANCHOR and then thirteen renders chained
    # off it, each binding the anchor's output first and each told in prose to
    # take the wardrobe and the background from it — which is the only thing
    # that held those two constant across a set. The first shot has no anchor
    # and must not carry the sentence, so this is empty rather than absent: a
    # template citing it is correct in both phases.
    #
    # The words are the `anchor` block's, authored like every other block. The
    # code decides only WHETHER, which is what `must_intro_<group>` already
    # does. `[Image1]` is safe to write into that block because the route binds
    # the anchor first, always.
    slot_ns = {"identity": slots_phrase(identity_positions or []),
               "anchor": (blocks.get("anchor") or "").strip() if anchored else ""}
    legacy = {**block_ns, **character_ns, "identity_slots": slot_ns["identity"]}

    return {
        **legacy,
        "block": SimpleNamespace(**block_ns),
        "character": SimpleNamespace(**character_ns),
        "slot": SimpleNamespace(**slot_ns),
    }


def character_values(profile: dict, blocks: dict, group: str = "body") -> dict:
    """One character's half of a prompt: what the bible says, as prose.

    **Shared by the two surfaces that fill a prompt from a character**, which is
    the whole reason it is a function. A reference angle fills `{character.top}`
    from the character being shot; a run plan fills `{character.1.top}` from the
    first character bound to the run. Two implementations of "what does this
    person usually wear" would disagree invisibly after the fact, because a run
    records the outcome and not the reasoning.
    """
    intro = blocks.get(f"must_intro_{group}") or blocks.get("must_intro_face") or ""
    return {
        "top": top_text(profile),
        "style": style_text(profile, blocks),
        "must": must_text(profile, intro),
        "build": build_text(profile, group),
        "age": age_text(profile),
        "identity_block": (profile.get("text_identity_block") or "").strip(),
    }


def expand_cast(template: str, profiles: list, blocks: dict) -> str:
    """A run plan's template, filled from the characters the run binds.

    `{character.1.top}` is the FIRST character bound to this run — the position
    in `run.characters`, one-based, the same rule `[Image1]` already follows on
    every one of these prompts.

    **Numbered rather than named, and that is not a style choice.** A slug is an
    attribute a rename swaps, and every record in this system names entity ids
    for exactly that reason — `domain/rewrite.py` existed to patch records that
    cited names and was deleted when citing names stopped being possible. A
    prompt saying `{character.<slug>.top}` would put that back: rename the
    character and the prompt is quietly wrong. There is a second, smaller reason
    — a template is one `git add` from being a production name in the repo.
    """
    return expand_cast_parts(template, profiles, blocks)[0]


def expand_cast_parts(template: str, profiles: list, blocks: dict) -> tuple:
    """`(text, spans)` — the same expansion, and where each citation landed.

    **The spans are why this walks `Formatter().parse` instead of calling
    `vformat`.** An expanded prompt is a wall of prose in which nothing says
    which words came from which citation, and that is the one question a reader
    of it has: which of these can I go and change. The walk produces output
    byte-identical to `vformat` — doubled braces included — so recording the
    offsets costs the caller nothing and the text stays exactly what is hashed.
    """
    cast = SimpleNamespace(**{
        str(i + 1): SimpleNamespace(**character_values(profile, blocks))
        for i, profile in enumerate(profiles)
    })
    values = {"character": cast}
    out, spans, at = [], [], 0
    try:
        for literal, field, spec, conv in string.Formatter().parse(template or ""):
            if literal:
                out.append(literal)
                at += len(literal)
            if field is None:
                continue
            filled = str(string.Formatter().get_field(field, (), values)[0])
            spans.append({"name": field, "start": at, "end": at + len(filled)})
            out.append(filled)
            at += len(filled)
        text = "".join(out)
    except KeyError as exc:
        raise ValidationError(
            f"this prompt cites {{{exc.args[0]}}}, which nothing provides. A run "
            f"plan may cite {{character.N.<field>}} — N is the character's "
            f"position in this run, counting from 1.")
    except AttributeError:
        raise ValidationError(
            f"this prompt cites a character or a field this run does not have. "
            f"It binds {len(profiles)} character(s), so N runs from 1 to "
            f"{len(profiles) or 1}, and the fields are: "
            f"{', '.join(sorted(character_values({}, blocks)))}.")
    except (IndexError, ValueError) as exc:
        raise ValidationError(
            f"malformed prompt: {exc}. A literal brace must be doubled — "
            f"{{{{ and }}}}.")
    tidy = "\n".join(line.rstrip() for line in text.strip().splitlines())
    if tidy != text:
        # The trim moves every offset after it. Rather than track the shift,
        # the spans are re-found in the tidied text — the filled strings are
        # long and specific, so this is exact in practice, and a span that
        # cannot be found is dropped rather than drawn in the wrong place.
        spans = _refind(tidy, [(s["name"], text[s["start"]:s["end"]]) for s in spans])
    return tidy, spans


def _refind(text: str, filled: list) -> list:
    """Where each filled value sits in `text`, searched left to right."""
    spans, at = [], 0
    for name, value in filled:
        found = text.find(value.strip(), at) if value.strip() else -1
        if found < 0:
            continue
        spans.append({"name": name, "start": found, "end": found + len(value.strip())})
        at = found + len(value.strip())
    return spans


def assemble(angle: dict, blocks: dict, profile: dict,
             identity_positions=None, anchored: bool = False) -> str:
    """One angle's finished prompt.

    A missing placeholder is a `ValidationError` naming both the placeholder and
    what WAS available, because the spec is editable now: the likeliest cause is
    somebody deleting a block an angle still cites, and the useful answer is the
    list of names they could have meant.
    """
    template = angle.get("prompt") or ""
    values = values_for(angle, blocks, profile, identity_positions, anchored)

    # **A bare name that two things answer to is refused rather than resolved.**
    # It used to resolve, and which one won was invisible: a block named `top`
    # lost to the bible every time, and a block named `angle_slot` won on an
    # angle with no plate and lost on one with a plate — the same words
    # rendering differently for a reason nothing in the template mentioned. The
    # dotted spelling makes the question answerable, so the ambiguous bare one
    # can just be an error that names both readings.
    clashes = sorted(_bare_names(template)
                     & set(blocks)
                     & (COMPUTED | set(NAMESPACES)))
    if clashes:
        name = clashes[0]
        where = ("a namespace" if name in NAMESPACES
                 else "a value filled from the character")
        raise ValidationError(
            f"angle {angle.get('id')!r} cites {{{name}}}, and that is both a "
            f"block and {where}. Say which: {{block.{name}}} for the block, "
            f"{{character.{name}}} for the character's."
        )

    try:
        text = string.Formatter().vformat(template, (), values)
    except KeyError as exc:
        raise ValidationError(
            f"angle {angle.get('id')!r} cites {{{exc.args[0]}}}, which nothing "
            f"provides. Available: {', '.join(sorted(values))}"
        )
    except AttributeError as exc:
        # A dotted name whose NAMESPACE exists and whose member does not. It is
        # an AttributeError rather than a KeyError purely because a dot in a
        # format field is attribute access — unhandled it reaches a person as a
        # 500 on a route whose whole input is their own typing.
        missing = str(exc).rsplit("'", 2)[-2] if "'" in str(exc) else str(exc)
        available = {
            space: ", ".join(sorted(vars(values[space]))) for space in NAMESPACES
        }
        raise ValidationError(
            f"angle {angle.get('id')!r} cites {missing!r} in a namespace that "
            f"does not provide it. "
            + " ".join(f"{space} has: {names or '(nothing)'}."
                       for space, names in available.items())
        )
    except (IndexError, ValueError) as exc:
        # A stray `{` or `}` in edited prose. `vformat` raises these rather than
        # KeyError, and unhandled they surface as a 500 on a route whose whole
        # input is a person's typing.
        raise ValidationError(
            f"angle {angle.get('id')!r} has a malformed template: {exc}. "
            f"A literal brace must be doubled — {{{{ and }}}}."
        )
    # **Whitespace is PRESERVED, and it used to be destroyed here.**
    #
    # This ended `" ".join(text.split())`, which collapses every newline into a
    # space. That was right while the source was a folded YAML scalar, where a
    # line break was an artifact of how the file wrapped rather than something
    # anybody chose — and it became wrong the moment the source became a row a
    # person types into a box.
    #
    # Not a readability preference. The single best-performing reference render
    # this repository has produced was authored by hand with SIX newlines in its
    # prompt, separating the angle, the scale and the identity instruction into
    # paragraphs; assembled through here it would have come out as one wall of
    # text. Blank lines and CAPS are what these models actually read as
    # structure, and the spec leans on both.
    #
    # Trailing space per line still goes — it is invisible, it is never
    # deliberate, and it would make two otherwise identical prompts hash to
    # different approval digests.
    return "\n".join(line.rstrip() for line in text.strip().splitlines())
