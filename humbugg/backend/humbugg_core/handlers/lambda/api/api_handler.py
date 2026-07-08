from mangum import Mangum
from asgiref.wsgi import WsgiToAsgi

from humbugg_core.app_factory import app

handler = Mangum(WsgiToAsgi(app), lifespan="off")
