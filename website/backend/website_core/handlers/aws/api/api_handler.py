"""AWS Lambda entrypoint for the website Flask API."""

from asgiref.wsgi import WsgiToAsgi
from mangum import Mangum

from website_core.app_factory import create_app

app = create_app()
handler = Mangum(WsgiToAsgi(app), lifespan="off")
