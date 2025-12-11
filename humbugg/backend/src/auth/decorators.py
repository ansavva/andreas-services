from functools import wraps
from typing import Callable

from flask import g, request

from src.config import load_config
from src.auth.jwt import CognitoJWTValidator

config = load_config()
validator = CognitoJWTValidator(
  region=config.cognito_region,
  user_pool_id=config.cognito_user_pool_id,
  audience=config.cognito_client_id
)


def requires_auth(fn: Callable):
  @wraps(fn)
  def wrapper(*args, **kwargs):
    auth_header = request.headers.get('Authorization', '')
    scheme, _, token = auth_header.partition(' ')
    if scheme.lower() != 'bearer' or not token:
      return {'message': 'Missing bearer token.'}, 401
    try:
      claims = validator.verify(token)
    except Exception as exc:
      return {'message': str(exc)}, 401
    g.current_user = {
      'profile_id': claims.get('sub'),
      'first_name': claims.get('given_name'),
      'last_name': claims.get('family_name')
    }
    return fn(*args, **kwargs)

  return wrapper
