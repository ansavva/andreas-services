"""Fill a TEMPLATE from the bible of each character a run binds.

**The half of a prompt that a character decides**, in the API so the SPA and
the CLI fill it the same way. A second implementation would be two opinions
about what a run was told to render, and the disagreement would be invisible
after the fact because the run records the outcome and not the reasoning. That
is the argument `GET /api/characters/<id>/selection` makes for resolving a
selection in one place, and it holds here unchanged.

## What a template may cite

Blocks by name, and these computed values:

    {character.N.top}            the character's usual garment, plainly
    {character.N.style}          the MEDIUM to render in — theirs, never ours
    {character.N.age}            `identity.apparent_age`
    {character.N.identity_block} the authored ~50-70 word compression, if any
    {character.N.build.face}     proportions, cropped for the picture being made
    {character.N.must.face}      the consistency checklist, with its intro
    {slot.identity}              `[Image1], [Image2] and [Image3]` — where the
                                 identity images actually landed

**N is the character's POSITION in the run**, one-based, the same number
`[Image1]` counts. It is not the name: a name is a label a rename swaps, and a
prompt citing one would be quietly wrong the moment somebody renamed the
character. `build` and `must` name a variant because the bible answers them
differently for a face than for a body, and defaulting silently is how a face
template ends up describing legs.

**There are no plate slots, no plate, and no anchor.** A generic pose figure
bound as a first image distorts the very thing it records, and a sentence
telling a render to take its wardrobe and background from an earlier one
describes a binding only a fourteen-at-a-time turnaround makes. Neither is
provided, so a template citing either gets the refusal every unknown citation
gets — a loaded gun is not left in place with an authored block arguing for it.
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

    The schema puts the COLOUR in that same field, so `colour:` is read on its
    own — dropping the detail whole would drop the colour with it, and an angle
    would come back in a colour nobody chose.
    """
    tops = ((profile.get("wardrobe") or {}).get("tops")) or []
    top = tops[0] if tops and isinstance(tops[0], dict) else {}
    item = (top.get("item") or "plain T-shirt").strip().rstrip(".").lower()
    colour = str(top.get("colour") or "").strip().rstrip(".").lower()
    return (f"Wearing a plain {colour + ' ' if colour else ''}{item}, unbranded, "
            f"with no logo, text or embroidery")


def style_text(profile: dict, blocks: dict) -> str:
    """What MEDIUM to render in — the character's, never this code's.

    Asserting "photographic, no stylisation" for every angle is right only for
    a character whose material is photographs. For one who
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
    one identity set, with the model free to average them. A prompt that names
    no age leaves the model to decide it.
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
    has no scale of its own, so the number is the only thing that settles it.

    ## One LABELLED line per field

    A run-on paragraph joining every field with a space loses which field a
    sentence belongs to; the hand-authored body prompts that work arrive as

        - Chest: Full square chest, rounded capped deltoids... SEEN FROM THE
          SIDE the chest has real DEPTH...
        - Legs: ...
        - Body hair: ...

    with each field named and on its own line. That is information the bible
    has, and it is the information a turned body angle needs most, because "the
    chest curves out in side view" only reads as an instruction about the chest
    if it is labelled as one. A wall of unattributed sentences produces a flat
    side profile from a good front one.

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

#: The variants a value has when the bible answers a question differently for a
#: face than for a body. A template names which — `{character.1.build.face}` —
#: and citing the bare name is refused rather than defaulted, because a face
#: template silently filled with body proportions is wrong in a way nothing in
#: the finished prose points at.
VARIANTS = ("face", "body")

#: The values that HAVE variants. Everything else a character provides is one
#: string whichever kind of picture is being made.
VARIED = ("build", "must")


def character_values(profile: dict, blocks: dict) -> dict:
    """One character's half of a prompt: what the bible says, as prose.

    **Shared by every surface that fills a prompt from a character**, which is
    the whole reason it is a function: two implementations of "what does this
    person usually wear" would disagree invisibly after the fact, because a run
    records the outcome and not the reasoning.

    `build` and `must` come back as namespaces rather than strings. Both read
    differently for a face than for a body — a face crops at mid-chest, so the
    proportions below it are noise, and the consistency checklist is introduced
    by a different sentence. A template says which it wants.
    """
    values = {
        "top": top_text(profile),
        "style": style_text(profile, blocks),
        "age": age_text(profile),
        "identity_block": (profile.get("text_identity_block") or "").strip(),
    }
    for name in VARIED:
        values[name] = SimpleNamespace(**{
            variant: (
                build_text(profile, variant) if name == "build"
                else must_text(profile, blocks.get(f"must_intro_{variant}")
                               or blocks.get("must_intro_face") or "")
            )
            for variant in VARIANTS
        })
    return values


def _unnumbered(template: str) -> set:
    """`{character.<field>}` citations, which do not resolve.

    **A prompt names its cast by POSITION**, one-based, the same rule
    `[Image1]` already follows — `{character.1.top}` is the first character
    bound to this run. There is one spelling, and the bare form is caught here
    rather than reaching `vformat` as an unhelpful `AttributeError`.
    """
    found = set()
    try:
        fields = list(string.Formatter().parse(template or ""))
    except ValueError:
        return found
    for _literal, field, _spec, _conv in fields:
        if not field:
            continue
        parts = field.split(".")
        if parts[0] == "character" and len(parts) > 1 and not parts[1].isdigit():
            found.add(field)
    return found


def _bare_variants(template: str) -> set:
    """`{character.N.build}` with no variant named. Refused, never defaulted."""
    found = set()
    try:
        fields = list(string.Formatter().parse(template or ""))
    except ValueError:
        return found
    for _literal, field, _spec, _conv in fields:
        if not field:
            continue
        parts = field.split(".")
        if (len(parts) == 3 and parts[0] == "character"
                and parts[1].isdigit() and parts[2] in VARIED):
            found.add(field)
    return found


def values_for(profiles: list, blocks: dict, identity_positions=None) -> dict:
    """Everything a template may cite, computed once.

    Three namespaces, and the dots are the point: `{block.scale_face}` and
    `{character.1.top}` say where a placeholder comes from, which is the
    question a reader of an assembled prompt actually has — and, more than that,
    they cannot collide. In one flat namespace a block called `top` would be
    silently beaten by the bible's `top_text`.

    A dot in a format field is ATTRIBUTE access rather than a nested key, so each
    namespace goes in as an object. Every block name matches `[a-z_][a-z0-9_]*`,
    which is also the rule for a Python identifier, so all of them are reachable.
    """
    block_ns = {k: v for k, v in blocks.items() if isinstance(v, str)}
    cast = SimpleNamespace(**{
        str(index + 1): SimpleNamespace(**character_values(profile, blocks))
        for index, profile in enumerate(profiles)
    })
    return {
        "block": SimpleNamespace(**block_ns),
        "character": cast,
        "slot": SimpleNamespace(identity=slots_phrase(identity_positions or [])),
    }



def expand(template: str, profiles: list, blocks: dict,
           identity_positions=None) -> str:
    """A template's finished prompt. **The one fill there is.**

    One spelling for the cast: positional, one-based, the same rule `[Image1]`
    follows.

    A missing placeholder is a `ValidationError` naming both the placeholder and
    what WAS available, because templates are edited by people: the likeliest
    cause is somebody deleting a block a template still cites, and the useful
    answer is the list of names they could have meant.
    """
    return expand_parts(template, profiles, blocks, identity_positions)[0]


def expand_parts(template: str, profiles: list, blocks: dict,
                 identity_positions=None) -> tuple:
    """`(text, spans)` — the same fill, and where each citation landed.

    **The spans are why this walks `Formatter().parse` instead of calling
    `vformat`.** An expanded prompt is a wall of prose in which nothing says
    which words came from which citation, and that is the one question a reader
    of it has: which of these can I go and change. The walk produces output
    byte-identical to `vformat` — doubled braces included — so recording the
    offsets costs the caller nothing and the text stays exactly what is hashed.
    """
    unnumbered = sorted(_unnumbered(template))
    if unnumbered:
        field = unnumbered[0]
        name = field.split(".", 1)[1]
        raise ValidationError(
            f"this prompt cites {{{field}}}, and a character is named by its "
            f"POSITION in the run. Write {{character.1.{name}}} for the first "
            f"one — the same number {{Image1}} counts.")

    bare = sorted(_bare_variants(template))
    if bare:
        field = bare[0]
        raise ValidationError(
            f"this prompt cites {{{field}}} without saying which. The bible "
            f"answers it differently for a face than for a body, so name one: "
            + " or ".join(f"{{{field}.{variant}}}" for variant in VARIANTS))

    values = values_for(profiles, blocks, identity_positions)
    out, spans, at = [], [], 0
    field = None
    try:
        for literal, field, _spec, _conv in string.Formatter().parse(template or ""):
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
            f"this prompt cites {{{exc.args[0]}}}, which nothing provides. "
            f"Available: {', '.join(sorted(values))}")
    except AttributeError:
        # **A cast position out of range gets its own sentence.** It is the
        # commonest of these by far — a prompt written against a two-character
        # run and then used on a one-character one — and "character has: 1" is a
        # true answer to a question nobody asked.
        parts = (field or "").split(".")
        if len(parts) > 1 and parts[0] == "character" and parts[1].isdigit():
            raise ValidationError(
                f"this prompt cites {{{field}}}, and this run binds "
                f"{len(profiles)} character(s). N counts from 1, in the order "
                f"the run lists them.")
        available = {
            space: ", ".join(sorted(vars(values[space]))) for space in NAMESPACES
        }
        raise ValidationError(
            f"this prompt cites {{{field}}}, which a namespace does not provide. "
            + " ".join(f"{space} has: {names or '(nothing)'}."
                       for space, names in available.items()))
    except (IndexError, ValueError) as exc:
        # A stray `{` or `}` in edited prose. `vformat` and the walk both raise
        # these, and unhandled they surface as a 500 on a route whose whole
        # input is a person's typing.
        raise ValidationError(
            f"this prompt has a malformed template: {exc}. "
            f"A literal brace must be doubled — {{{{ and }}}}.")

    # **Whitespace is PRESERVED.** Ending with `" ".join(text.split())` would
    # collapse every newline into a space, which is wrong for a row a person
    # types into a box.
    #
    # Not a readability preference. The single best-performing reference render
    # this repository has produced was authored by hand with SIX newlines in its
    # prompt, separating the angle, the scale and the identity instruction into
    # paragraphs; assembled through here it would have come out as one wall of
    # text. Blank lines and CAPS are what these models actually read as
    # structure, and the templates lean on both.
    #
    # Trailing space per line still goes — it is invisible, it is never
    # deliberate, and it would make two otherwise identical prompts hash to
    # different fingerprints.
    return "\n".join(line.rstrip() for line in text.strip().splitlines()), spans
