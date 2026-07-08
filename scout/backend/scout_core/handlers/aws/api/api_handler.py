"""AWS Lambda entrypoint for the Scout events HTTP API (Flask + Mangum).

Routing lives in ``scout_core.routes.*`` (resource Blueprints wired up by
``scout_core.app_factory``); this module is a thin adapter that serves that
Flask app through Mangum for API Gateway.
"""

from asgiref.wsgi import WsgiToAsgi
from mangum import Mangum

from scout_core.app_factory import create_app

_mangum_handler = None


def _get_handler():
    global _mangum_handler
    if _mangum_handler is None:
        _mangum_handler = Mangum(WsgiToAsgi(create_app()), lifespan="off")
    return _mangum_handler


def handler(event, context):
    return _get_handler()(event, context)
