"""Shared request parsing and response helpers for the route Blueprints.

Services return plain dicts; these wrap them in Flask responses. Missing-field
(KeyError) and bad-value (ValueError) errors raised by the services are mapped
to 400 by app-level handlers, so routes can read required fields directly and
let those propagate.
"""

from flask import jsonify, request


def body() -> dict:
    """Parsed JSON request body, or {} when absent or unparseable."""
    return request.get_json(silent=True) or {}


def ok(payload):
    return jsonify(payload), 200


def created(payload):
    return jsonify(payload), 201


def not_found(message="Not found"):
    return jsonify({"error": message}), 404
