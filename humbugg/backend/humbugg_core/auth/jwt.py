import time
from functools import lru_cache
from typing import Any, Dict

import requests
from jose import jwk, jwt
from jose.utils import base64url_decode


class CognitoJWTValidator:
  def __init__(self, region: str, user_pool_id: str, audience: str):
    self.region = region
    self.user_pool_id = user_pool_id
    self.audience = audience
    self.issuer = f'https://cognito-idp.{region}.amazonaws.com/{user_pool_id}'

  @property
  @lru_cache(maxsize=1)
  def jwks(self) -> Dict[str, Any]:
    response = requests.get(f'{self.issuer}/.well-known/jwks.json', timeout=5)
    response.raise_for_status()
    payload = response.json()
    payload['_cached_at'] = time.time()
    return payload

  def verify(self, token: str) -> Dict[str, Any]:
    headers = jwt.get_unverified_header(token)
    keys = self.jwks.get('keys', [])
    key = next((k for k in keys if k['kid'] == headers['kid']), None)
    if not key:
      raise ValueError('Unable to locate matching JWKS key.')
    public_key = jwk.construct(key)
    message, encoded_signature = token.rsplit('.', 1)
    decoded_signature = base64url_decode(encoded_signature.encode())
    if not public_key.verify(message.encode(), decoded_signature):
      raise ValueError('Invalid token signature.')
    claims = jwt.get_unverified_claims(token)
    if claims.get('iss') != self.issuer:
      raise ValueError('Invalid issuer.')
    if claims.get('aud') != self.audience:
      raise ValueError('Invalid audience.')
    if claims.get('exp', 0) < time.time():
      raise ValueError('Token expired.')
    return claims
