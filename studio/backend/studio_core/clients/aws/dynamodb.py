"""Thin boto3 wrapper over the catalog table.

The catalog is where the library actually lives. A node's identity, name,
parent and owner are rows here, and an S3 key is an opaque `blob_key` sitting on
one of them that nothing derives and nothing parses. That is the whole point of
the table: a rename, a move, a share and a transfer become row writes that touch
zero objects, where making ownership a *location* would have made each of them a
copy of the bytes.

Two decisions are baked into `client()`, and both are load-bearing.

* **It is the low-level client, not `boto3.resource("dynamodb")`.** Every node is
  two items — one keyed by its parent so a folder can be listed, one keyed by its
  own id so it can be fetched — so every write is a `TransactWriteItems`, and the
  resource's `Table` does not expose transactions at all. A repository built on
  the resource would drop to `meta.client` for exactly the half that matters and
  carry two marshalling conventions to do it. One client, one vocabulary.
* **The region is pinned from `config.aws_region()`**, for the same reason the S3
  client pins it: a table is regional, and a client that guessed the region wrong
  answers `ResourceNotFoundException` — which reads as "there is no such table"
  rather than "you are looking in the wrong region", and sends the reader off to
  check Terraform.

**There are no operation wrappers here yet, and that is deliberate.** Nothing in
this service reads or writes the table: listings still come straight from S3, and
the catalog repository and the services over it arrive with the API. Until then
the table is inert. This module is the connection and the cache hook the tests
need; guessing at the signatures of query and transaction helpers before there is
a caller is how they end up wrong in a way nobody notices.
"""

import boto3
from botocore.config import Config

from studio_core import config

_client = None


def client():
    """Lazily built, module-cached DynamoDB client.

    Cached for the same reason the S3 client is: a container Lambda serves many
    requests, and building a client per request pays for credential resolution
    and endpoint discovery every time.
    """
    global _client
    if _client is None:
        _client = boto3.client(
            "dynamodb",
            region_name=config.aws_region(),
            config=Config(retries={"max_attempts": 3}),
        )
    return _client


def reset_client():
    """Drop the cached client. Tests use this between moto mocks."""
    global _client
    _client = None
