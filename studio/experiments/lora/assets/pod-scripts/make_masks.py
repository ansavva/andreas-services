"""Write a white-face-on-black mask per dataset image, for masked training.

OneTrainer's convention: `<image>-masklabel.png` next to the image. Uses the
insightface stack already installed for PuLID; the mask is the detected face
box grown by 40%, feathered — crude, and enough: the point is to stop 15
images of one wardrobe from teaching the background.
"""

import pathlib
import sys

import numpy as np
from insightface.app import FaceAnalysis
from PIL import Image, ImageDraw, ImageFilter

GROW = 0.4
FEATHER = 25


def main(dataset: pathlib.Path) -> None:
    app = FaceAnalysis(name="antelopev2",
                       root="/weights/models/insightface",
                       providers=["CUDAExecutionProvider", "CPUExecutionProvider"])
    app.prepare(ctx_id=0, det_size=(640, 640))
    images = sorted([*dataset.glob("*.png"), *dataset.glob("*.jpg"), *dataset.glob("*.jpeg")])
    images = [i for i in images if not i.stem.endswith("-masklabel")]
    done = skipped = 0
    for path in images:
        img = Image.open(path).convert("RGB")
        faces = app.get(np.array(img)[:, :, ::-1])
        mask = Image.new("L", img.size, 0)
        if not faces:
            print(f"NO FACE: {path.name} — full-white mask (unmasked training for this image)")
            mask = Image.new("L", img.size, 255)
            skipped += 1
        else:
            draw = ImageDraw.Draw(mask)
            for face in faces:
                x1, y1, x2, y2 = face.bbox
                gw, gh = (x2 - x1) * GROW, (y2 - y1) * GROW
                draw.rectangle([x1 - gw, y1 - gh, x2 + gw, y2 + gh], fill=255)
            mask = mask.filter(ImageFilter.GaussianBlur(FEATHER))
        mask.save(path.with_name(f"{path.stem}-masklabel.png"))
        done += 1
    print(f"{done} masks written ({skipped} faceless)")


if __name__ == "__main__":
    main(pathlib.Path(sys.argv[1]))
