/**
 * What a bible's sections are FOR, per subject kind — the one thing the form
 * needs that the record does not carry.
 *
 * `ProfileForm` is built from the value it is given: it walks the profile and
 * draws a control per leaf, so a section the API adds tomorrow appears without
 * a deploy. What it cannot read off the value is the sentence under each
 * section heading and which sections sit together — a character's bible is
 * appearance, direction and a summary; a location's is the space, the light
 * and a summary. Two schemas, one form.
 *
 * A section here is a heading and a hint, nothing below it: a list of "fields
 * a shoot reads" would drift the first time the pipeline changed, where a
 * sentence about what a section is for changes about as often as the section.
 */

/** The one paragraph every bible ends in — the same key for both kinds, deliberately. */
export const SUMMARY_KEY = "text_identity_block";

export interface ProfileSchema {
  /** The noun a sentence uses — "Re-read the character", `studio location textblock`. */
  noun: "character" | "location";
  sections: ReadonlyArray<{ key: string; hint: string }>;
  /** The sections in groups, because eight peers is a list and not a shape. */
  groups: ReadonlyArray<{ label: string; blurb: string; keys: readonly string[] }>;
  /** What the summary restates — the stale marker watches these and nothing else. */
  summarised: readonly string[];
  /** The line under the name field. */
  nameHint: string;
}

export const CHARACTER_SCHEMA: ProfileSchema = {
  noun: "character",
  sections: [
    {
      key: "identity",
      hint: "The card: age, build, height read, signature features. A turnaround states apparent age and height read in the prompt, because a reference set spanning years will not agree on either.",
    },
    {
      key: "face",
      hint: "Structure, skin, eyes, hair, facial hair. No code reads this — it is what a prompt gets written from, and what a finished render is read back against.",
    },
    {
      key: "body",
      hint: "Proportions. A turnaround states them in the prompt so the angle image's own build does not decide the figure's — a face angle takes what shows above a mid-chest crop, a body angle takes all of it.",
    },
    {
      key: "wardrobe",
      hint: "What the character usually wears. A turnaround takes the first tops entry for its plain-top angle; the rest is prompt material.",
    },
    {
      key: "rendering",
      hint: "The medium the character exists in — a per-render choice rather than part of who they are, which is why it is not folded into the face and body prose. A shoot reads default_style; framing and backgrounds are prompt material, like face and voice.",
    },
    {
      key: "consistency",
      hint: "must / never / drift_modes — the checklist a render is verified against, each drift paired with the fix to write into the next prompt. A shoot puts must in the prompt itself.",
    },
    {
      key: "voice",
      hint: "Language, accent, manner, delivery. Read when a prompt carries a spoken line — Seedance generates the audio in character.",
    },
    {
      key: SUMMARY_KEY,
      hint: "A 50-70 word paragraph for engines that carry no reference images, where the character has to survive as prose. It restates the appearance sections; nothing here can write it, because studio's API calls no model.",
    },
  ],
  groups: [
    {
      label: "Appearance",
      blurb: "Who the character is. Style-agnostic on purpose — how to render them is the next group.",
      keys: ["identity", "face", "body", "wardrobe"],
    },
    {
      label: "Direction",
      blurb: "How to render, and how to tell whether the render is right.",
      keys: ["rendering", "consistency", "voice"],
    },
    {
      label: "Summary",
      blurb: "The appearance sections compressed into one pasteable paragraph.",
      keys: [SUMMARY_KEY],
    },
  ],
  summarised: ["identity", "face", "body", "wardrobe", "consistency"],
  nameHint: "What this character is called. Renaming copies no objects.",
};

/**
 * A location has no face and no wardrobe. What holds it on-model across renders
 * is its geography — what is fixed, where the light comes from, what the camera
 * can stand — so that is what the sections are.
 */
export const LOCATION_SCHEMA: ProfileSchema = {
  noun: "location",
  sections: [
    {
      key: "identity",
      hint: "The card: what kind of place, how big it reads, when and where it belongs, the two to four cues that make it recognisable.",
    },
    {
      key: "space",
      hint: "What is FIXED and cannot move between renders — the plan, the floor, the walls, the openings, the built-in furniture. A render is read back against this first.",
    },
    {
      key: "dressing",
      hint: "What is in the space and could be moved — props with their placement, any legible signage verbatim, how full the place is. Prompt material, one entry per thing that carries recognition.",
    },
    {
      key: "lighting",
      hint: "Where the light comes from and its states — day, night, practicals only. Name a state in a prompt rather than describing the light again.",
    },
    {
      key: "palette",
      hint: "The two or three colours that fill the frame, the accents, the textures. What a text-only engine cannot infer from a plan.",
    },
    {
      key: "rendering",
      hint: "The medium, the lens, and the named camera vantages — a shot is called for by vantage rather than described from scratch. A shoot reads default_style.",
    },
    {
      key: "consistency",
      hint: "must / never / drift_modes — the checklist a render is verified against, each drift paired with the fix to write into the next prompt.",
    },
    {
      key: SUMMARY_KEY,
      hint: "A 50-70 word paragraph for engines that carry no reference images, where the place has to survive as prose. It restates the space and lighting sections; nothing here can write it, because studio's API calls no model.",
    },
  ],
  groups: [
    {
      label: "The place",
      blurb: "What the location is. Style-agnostic on purpose — how to render it is the next group.",
      keys: ["identity", "space", "dressing", "lighting", "palette"],
    },
    {
      label: "Direction",
      blurb: "How to shoot it, and how to tell whether the render is right.",
      keys: ["rendering", "consistency"],
    },
    {
      label: "Summary",
      blurb: "The space and lighting sections compressed into one pasteable paragraph.",
      keys: [SUMMARY_KEY],
    },
  ],
  summarised: ["identity", "space", "dressing", "lighting", "palette", "consistency"],
  nameHint: "What this location is called. Renaming copies no objects.",
};
