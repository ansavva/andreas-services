import os

from flask import Flask
from flask_cors import CORS

from src.config import load_config
from src.routes.group_members import bp as group_members_bp
from src.routes.groups import bp as groups_bp
from src.routes.profiles import bp as profiles_bp


def create_app() -> Flask:
  config = load_config()
  app = Flask(__name__)
  app.config.update(
    MONGO_URI=config.mongo_uri,
    MONGO_DB_NAME=config.mongo_db_name,
    ENV=config.environ,
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


if __name__ == '__main__':
  env = os.getenv('APP_ENV', 'development')
  debug_mode = env == 'development'
  app.run(debug=debug_mode, host='0.0.0.0', port=int(os.getenv('PORT', '5001')))
