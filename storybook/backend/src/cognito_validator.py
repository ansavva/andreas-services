import json
from functools import wraps
from flask import request, jsonify
from jose import jwt, JWTError
from jose.utils import base64url_decode
import requests
import os

class CognitoJWTValidator:
    def __init__(self, region, user_pool_id, app_client_id):
        self.region = region
        self.user_pool_id = user_pool_id
        self.app_client_id = app_client_id
        self.keys_url = f'https://cognito-idp.{region}.amazonaws.com/{user_pool_id}/.well-known/jwks.json'
        self.keys = None

    def get_keys(self):
        """Fetch and cache the JWKs from Cognito"""
        if self.keys is None:
            response = requests.get(self.keys_url)
            self.keys = response.json()['keys']
        return self.keys

    def get_key(self, token):
        """Get the public key that matches the token's key ID"""
        headers = jwt.get_unverified_headers(token)
        kid = headers['kid']

        keys = self.get_keys()
        key = next((k for k in keys if k['kid'] == kid), None)

        if not key:
            raise ValueError('Public key not found in jwks.json')

        return key

    def validate_token(self, token):
        """Validate the Cognito JWT token"""
        try:
            # Get the key
            key = self.get_key(token)

            # Decode and verify the token
            claims = jwt.decode(
                token,
                key,
                algorithms=['RS256'],
                audience=self.app_client_id,
                issuer=f'https://cognito-idp.{self.region}.amazonaws.com/{self.user_pool_id}'
            )

            return claims

        except JWTError as e:
            raise ValueError(f'Token validation failed: {str(e)}')

def require_cognito_auth(validator):
    """Decorator to require Cognito authentication"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Skip auth for OPTIONS requests (CORS preflight)
            if request.method == 'OPTIONS':
                return f(*args, **kwargs)

            # Get the token from the Authorization header
            auth_header = request.headers.get('Authorization')
            if not auth_header:
                return jsonify({'error': 'No authorization header'}), 401

            try:
                # Extract the token (format: "Bearer <token>")
                parts = auth_header.split()
                if len(parts) != 2 or parts[0].lower() != 'bearer':
                    return jsonify({'error': 'Invalid authorization header format'}), 401

                token = parts[1]

                # Validate the token
                claims = validator.validate_token(token)

                # Add the claims to the request context for use in the route
                request.cognito_claims = claims

            except Exception as e:
                return jsonify({'error': f'Authentication failed: {str(e)}'}), 401

            return f(*args, **kwargs)

        return decorated_function
    return decorator
