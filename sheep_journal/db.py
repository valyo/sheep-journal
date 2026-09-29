import sqlite3

import click
from flask import current_app, g


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
    return g.db


def close_db(exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """Create any missing tables. Safe to run on every start."""
    with current_app.open_resource("schema.sql") as f:
        get_db().executescript(f.read().decode("utf-8"))


@click.command("init-db")
def init_db_command():
    init_db()
    click.echo("Database initialised.")


@click.command("seed-demo")
def seed_demo_command():
    """Fill an empty database with a small demo herd."""
    from .demo import seed

    if seed():
        click.echo("Demo data added.")
    else:
        click.echo("Database already has data; nothing added.")


def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
    app.cli.add_command(seed_demo_command)
    with app.app_context():
        init_db()
