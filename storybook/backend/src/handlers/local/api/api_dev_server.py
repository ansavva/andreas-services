from src.utils.http.app_factory import create_app
from src.utils.config import AppConfig

app = create_app()

if __name__ == "__main__":
    debug_mode = AppConfig.FLASK_ENV == "development"
    app.run(debug=debug_mode, port=AppConfig.PORT, host="0.0.0.0")
