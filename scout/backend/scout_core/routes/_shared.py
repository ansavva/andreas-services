"""Shared request parsing + response helpers for the route Blueprints.

Service/repository functions return plain dicts/lists; these helpers wrap them in
Flask responses. Decimal serialization is handled by app_factory's
DecimalJSONProvider, and missing-field / bad-value errors raised by the services
(KeyError / ValueError) are mapped to 400 by app-level error handlers, so routes
can read required fields with `body()["field"]` and let those propagate.
"""

from flask import Response, jsonify, request


def body() -> dict:
    """Parsed JSON request body, or {} when absent/unparseable."""
    return request.get_json(silent=True) or {}


def csv_param(key):
    """A comma-separated query param split into a list, or None when absent."""
    value = request.args.get(key)
    return [v for v in value.split(",") if v] if value else None


def ok(payload):
    return jsonify(payload), 200


def created(payload):
    return jsonify(payload), 201


def bad_request(message):
    return jsonify({"error": message}), 400


def not_found(message="Not found"):
    return jsonify({"error": message}), 404


def binary(data, content_type):
    return Response(data, mimetype=content_type)
