import os

from flask import Flask


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev"),
        DATABASE=os.environ.get(
            "SHEEP_JOURNAL_DATABASE",
            os.path.join(app.instance_path, "sheep_journal.sqlite"),
        ),
        TIMEZONE=os.environ.get("SHEEP_JOURNAL_TZ", "Europe/Stockholm"),
        # Tests can pin the clock with a timezone-aware datetime.
        FIXED_NOW=None,
    )
    if test_config:
        app.config.update(test_config)

    os.makedirs(os.path.dirname(os.path.abspath(app.config["DATABASE"])), exist_ok=True)

    from . import db, filters

    db.init_app(app)
    filters.init_app(app)

    from .views import animals, journal, main

    app.register_blueprint(main.bp)
    app.register_blueprint(journal.bp)
    app.register_blueprint(animals.bp)

    return app
