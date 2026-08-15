"""AWS Lambda entrypoint for the studio Flask API."""

from asgiref.wsgi import WsgiToAsgi
from mangum import Mangum

from studio_core.app_factory import create_app

app = create_app()
handler = Mangum(WsgiToAsgi(app), lifespan="off")
