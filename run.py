import os
from app import create_app

env = os.environ.get("FLASK_ENV", "development")
config_map = {
    "development": "config.DevelopmentConfig",
    "production": "config.ProductionConfig",
}

app = create_app(config_map.get(env, "config.DevelopmentConfig"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
