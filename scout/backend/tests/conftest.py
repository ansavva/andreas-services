"""Shared pytest configuration.

The modules under test resolve their DynamoDB table and Lambda function names
from the environment and refuse to start without them — there is deliberately no
fallback to a guessed resource name, because a wrong-but-plausible default sends
reads and writes at a table that may not exist (or, worse, one that does).

The tests build their moto fixtures under these literal names, so set them here,
before any module under test is imported.
"""

import os

os.environ.setdefault("SCOUT_CORE_TABLE", "scout-core")
os.environ.setdefault("SCOUT_SETTINGS_TABLE", "scout-settings")
os.environ.setdefault("SCOUT_PROCESSOR_FN", "scout-source-run-processor")
