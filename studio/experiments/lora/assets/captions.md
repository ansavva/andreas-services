# Captioning the curated dataset

One `.txt` next to each image (`lora-lab captions <slug>` scaffolds them).
Every caption starts with the trigger token and then names ONLY what is
non-permanent in that image. The rule and the reason:

> If you do not caption the red jacket, the model decides the red jacket is
> part of the person.

- **Always**: `photo of ohwx_<slug>, ...`
- **Caption**: wardrobe, pose, expression-as-action, lighting, background,
  camera distance.
- **Never caption**: permanent identity traits (face shape, eye color, hair
  unless it varies between images). Those are what the LoRA should absorb.

Example (for a candidate from the `threequarter-right` variation):

    photo of ohwx_<slug>, three-quarter view, wearing a grey t-shirt,
    golden hour sunlight, outdoor background, waist-up shot

Ten minutes of captioning is the highest-leverage step of the whole recipe.
