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

    {top}              the character's usual garment, plainly
    {style}            the MEDIUM to render in — the character's, never ours
    {must}             the consistency checklist, introduced by the group's intro
    {build}            proportions, from the bible, group-dependent
    {age}              `identity.apparent_age`
    {identity_block}   the authored ~50-70 word compression, if the bible has one
    {identity_slots}   `[Image2], [Image3] and [Image4]` — where the identity
                       images actually landed
    {angle_slot}       `[Image1]` — ABSENT when the angle binds no plate
    {torso_slot}       likewise for a second guide

The two slots are absent rather than empty when there is no such image, so a
template citing one it never declared fails loudly instead of rendering "".
"""

import string

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


def build_text(profile: dict, group: str = "body") -> str:
    """The person's PROPORTIONS — from the bible, never from here.

    HEIGHT comes first, and from `identity` rather than `body`: it is the one
    proportion the bible states as a NUMBER, and a figure on a plain backdrop
    has no scale of its own, so the number is the only thing that settles it. It
    was the only field never sent, because the build clause read `body:` alone.
    """
    body = profile.get("body") or {}
    height = _clean((profile.get("identity") or {}).get("height_read"))
    fields = BODY_FIELDS
    if group != "face":
        fields += BODY_ONLY_FIELDS
    fields += _extra_body_fields(body, fields)
    parts = [height] + [str(body.get(k) or "").strip() for k in fields]
    return " ".join(_clean(p) for p in parts if p)


def slots_phrase(positions: list) -> str:
    """[Image2] / [Image2] and [Image3] / [Image2], [Image3] and [Image4]."""
    names = [f"[Image{n}]" for n in positions]
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + " and " + names[-1]


def values_for(angle: dict, blocks: dict, profile: dict,
               angle_position=None, identity_positions=None,
               torso_position=None) -> dict:
    """Everything a template may cite, computed once."""
    group = angle.get("group") or "face"
    intro = blocks.get(f"must_intro_{group}") or blocks.get("must_intro_face") or ""
    values = {
        **{k: v for k, v in blocks.items() if isinstance(v, str)},
        "top": top_text(profile),
        "style": style_text(profile, blocks),
        "must": must_text(profile, intro),
        "build": build_text(profile, group),
        "age": age_text(profile),
        "identity_block": (profile.get("text_identity_block") or "").strip(),
        "identity_slots": slots_phrase(identity_positions or []),
    }
    # Absent rather than empty, so a template citing an image the angle never
    # declared fails loudly instead of rendering "".
    if angle_position is not None:
        values["angle_slot"] = f"[Image{angle_position}]"
    if torso_position is not None:
        values["torso_slot"] = f"[Image{torso_position}]"
    return values


def assemble(angle: dict, blocks: dict, profile: dict,
             angle_position=None, identity_positions=None,
             torso_position=None) -> str:
    """One angle's finished prompt.

    A missing placeholder is a `ValidationError` naming both the placeholder and
    what WAS available, because the spec is editable now: the likeliest cause is
    somebody deleting a block an angle still cites, and the useful answer is the
    list of names they could have meant.
    """
    values = values_for(angle, blocks, profile, angle_position,
                        identity_positions, torso_position)
    try:
        text = string.Formatter().vformat(angle.get("prompt") or "", (), values)
    except KeyError as exc:
        raise ValidationError(
            f"angle {angle.get('id')!r} cites {{{exc.args[0]}}}, which nothing "
            f"provides. Available: {', '.join(sorted(values))}"
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
