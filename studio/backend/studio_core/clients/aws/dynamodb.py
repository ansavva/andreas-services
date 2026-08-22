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

**There are still no operation wrappers here, and the reason changed when the
table came alive.** It used to be that nothing read or wrote it, and guessing at
the signatures of query and transaction helpers before there was a caller was how
they end up wrong in a way nobody notices. There are callers now: `services.catalog`
reaches `client()` at eight sites — `get_item`, `batch_get_item`,
`transact_write_items` and a paginated `query` — and every listing in
`services.browse` is one of those queries. What keeps the wrappers out is the
boundary that module holds: it is the only place that knows a `pk`, an `sk` or a
`NAME#` prefix, and a helper here would be a second place holding half of the same
layout. This module is the connection and the cache hook, and nothing else.
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
