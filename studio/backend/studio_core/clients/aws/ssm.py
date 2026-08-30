"""Thin boto3 wrapper over Parameter Store, for the one secret this service holds.

**Studio held no provider credential at all until generation moved here.** The
Lambda could read and write its own bucket and its own table and nothing else,
so "what could a compromise of this function reach" had an answer that stopped
at the library. The Replicate token changes that, and this module is the whole of
the change — so the properties that bound it are worth stating in one place:

* **The value never enters the function's environment.** It would have been
  cheaper to have the deploy workflow read the parameter and hand it to
  `update-function-configuration`, which is how every other studio setting
  arrives — but a Lambda's environment is readable by anyone holding
  `lambda:GetFunctionConfiguration`, and it is printed by the console. A
  SecureString read at call time is reachable only by the execution role, which
  is granted `ssm:GetParameter` on exactly one parameter name.
* **It is cached for the life of the container and never on disk.** A token is
  read once per cold start rather than once per submission; `reset_cache` exists
  for the tests.
* **A missing parameter is a `ConfigError`, not an empty string.** An unset token
  reaching the provider is a 401 from Replicate reported as an upstream failure,
  which reads as "the provider is down" rather than "this service is not
  configured".

There is deliberately no `put`. The token is set out of band by a person; a
service that could write its own credential could also rotate it into something
nobody else knows.
"""

import logging

import boto3
from botocore.exceptions import ClientError

from studio_core import config
from studio_core.errors import ConfigError, UpstreamError

logger = logging.getLogger(__name__)

_client = None
_cache: dict[str, str] = {}


def client():
    """Lazily built, module-cached SSM client."""
    global _client
    if _client is None:
        _client = boto3.client("ssm", region_name=config.aws_region())
    return _client


def reset_cache():
    """Drop the cached client and every cached value. For tests."""
    global _client
    _client = None
    _cache.clear()


def secure_parameter(name: str) -> str:
    """One decrypted SecureString, cached per container.

    `WithDecryption=True` is what makes this need `kms:Decrypt` as well as
    `ssm:GetParameter` — the two are granted together in `modules/compute`, and
    granting only the first fails at runtime with an `AccessDeniedException`
    naming KMS rather than SSM, which sends the reader to the wrong policy.
    """
    if name in _cache:
        return _cache[name]

    try:
        response = client().get_parameter(Name=name, WithDecryption=True)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code")
        if code == "ParameterNotFound":
            raise ConfigError(
                f"the SSM parameter {name} does not exist; "
                "nothing can be submitted until it holds a Replicate API token"
            ) from exc
        logger.warning("GetParameter failed for %s: %s", name, exc)
        raise UpstreamError("Could not read the provider credential") from exc

    value = (response.get("Parameter") or {}).get("Value") or ""
    if not value:
        raise ConfigError(f"the SSM parameter {name} is empty")
    _cache[name] = value
    return value
