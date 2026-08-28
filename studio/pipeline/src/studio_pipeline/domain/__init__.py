"""What a run, scene, movie, project and character ARE. No I/O beyond the adapters.

`TEMPLATES_DIR` lives here rather than in any one module because more than one
reads it — the character bible template and the reference-angle spec sit side by
side, and `engine/turnaround.py` reached the second through `characters.__file__`.
That worked only while `characters` was a single file at this level; splitting
it into a package moved the anchor a segment deeper and would have taken the
angle spec with it. One directory, named once, beside the directory it names.
"""

from pathlib import Path

TEMPLATES_DIR = Path(__file__).parent / "templates"
