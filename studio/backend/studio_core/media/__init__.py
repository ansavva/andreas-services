"""Local media processing: ffmpeg and Pillow, and nothing that knows about HTTP.

**This is the half of studio that used to live in the CLI.** `adapters/ffmpeg.py`,
`domain/frames.py`, `domain/contact_sheet.py`, `objects/convert.py` and
`objects/crop.py` were ~1,360 lines of download-process-upload running on a
developer's machine, for one reason stated in `routes/scenes.py`: the Lambda had
no `ffmpeg`. That is a fact about an image, and an image is a thing we can
change.

What is here takes **paths and bytes** and returns paths, bytes and reports. It
resolves no node, reads no catalog row and signs no URL — `services/render.py`
does all of that and calls in here. Two reasons that seam is where it is:

* **The API image gets Pillow and not ffmpeg.** `imaging.py` is a sub-second
  operation on one image and is answered synchronously by the API; `ffmpeg.py`
  is minutes of video and runs in a second image on a queue. A module that
  reached the catalog could not be split that way.
* **A pure function of a file is testable without AWS.** The suite feeds these
  real bytes and reads the report back; nothing has to be mocked to do it.
"""
