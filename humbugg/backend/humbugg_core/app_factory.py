from flask import Flask
from flask_cors import CORS

from humbugg_core.config import load_config
from humbugg_core.routes.group_members import bp as group_members_bp
from humbugg_core.routes.groups import bp as groups_bp
from humbugg_core.routes.profiles import bp as profiles_bp


def create_app() -> Flask:
  config = load_config()
  app = Flask(__name__)
  app.config.update(
    DEBUG=config.environ == 'development'
  )

  CORS(app, supports_credentials=True)
  app.register_blueprint(groups_bp)
  app.register_blueprint(group_members_bp)
  app.register_blueprint(profiles_bp)

  @app.route('/health', methods=['GET'])
  def health():
    return {'status': 'ok'}

  return app


app = create_app()
