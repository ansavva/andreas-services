"""AWS Lambda entrypoint for the classroom HTTP API (Flask + Mangum).

Routing lives in ``classroom_core.routes.*``; this module is a thin adapter
that serves the Flask app through Mangum for API Gateway.
"""

from asgiref.wsgi import WsgiToAsgi
from mangum import Mangum

from classroom_core.app_factory import create_app

_mangum_handler = None


def _get_handler():
    global _mangum_handler
    if _mangum_handler is None:
        _mangum_handler = Mangum(WsgiToAsgi(create_app()), lifespan="off")
    return _mangum_handler


def handler(event, context):
    return _get_handler()(event, context)
