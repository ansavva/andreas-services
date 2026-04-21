from mangum import Mangum
from src.app import app

handler = Mangum(app, lifespan="off")
