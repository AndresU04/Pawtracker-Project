"""PawTrack application factory.

Push 1.3 (Person 1): trimmed version. Registers only the auth and users blueprints.
Later pushes add their own lines where marked:
  - Person 2: cache import + cache.init_app(app); shelters, animals blueprints
  - Person 4: register_cli import + register_cli(app); medical blueprint
  - Person 3: applications blueprint
"""
import os

from flask import Flask, jsonify
from . import cache
from .config import config_by_name
from .errors import register_error_handlers
from .extensions import db

def create_app(config_name=None, overrides=None):
    config_name = config_name or os.environ.get("APP_ENV", "development")
    if config_name not in config_by_name:
        raise RuntimeError(f"Unknown APP_ENV '{config_name}'. Use one of {list(config_by_name)}.")

    app = Flask(__name__)
    app.config.from_object(config_by_name[config_name])
    if overrides:
        app.config.update(overrides)
    app.url_map.strict_slashes = False

    if not app.config.get("SECRET_KEY"):
        raise RuntimeError("SECRET_KEY is not set. Copy .env.example to .env and set it.")
    if not app.config.get("SQLALCHEMY_DATABASE_URI"):
        raise RuntimeError("DATABASE_URL is not set. Copy .env.example to .env and set it.")

    from . import models  # noqa: F401  (register tables on metadata)

    db.init_app(app)
    cache.init_app(app)
    register_error_handlers(app)
    # Person 4 adds:  register_cli(app)

    # Each person adds their blueprint name to this import and to the tuple below.
    from .blueprints import auth, users

    for module in (auth, users):
        app.register_blueprint(module.bp)

    @app.get("/api/v1/health")
    def health():
        return jsonify({"status": "ok"})

    return app