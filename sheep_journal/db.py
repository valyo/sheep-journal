import sqlite3
from importlib import resources

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


def migrations():
    """Migration scripts as (version, sql), in order. Named NNNN_description.sql."""
    folder = resources.files("sheep_journal") / "migrations"
    scripts = sorted(p for p in folder.iterdir() if p.name.endswith(".sql"))
    return [(int(p.name[:4]), p.read_text(encoding="utf-8")) for p in scripts]


def init_db():
    """Create a new database, or apply pending migrations to an existing one.

    schema.sql always holds the full current schema, so a new database gets it
    in one go and is stamped with the latest version. PRAGMA user_version tracks
    which migrations an existing database has had.
    """
    db = get_db()
    steps = migrations()
    latest = steps[-1][0] if steps else 0
    exists = db.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'entry'"
    ).fetchone()
    if not exists:
        with current_app.open_resource("schema.sql") as f:
            db.executescript(f.read().decode("utf-8"))
        db.execute(f"PRAGMA user_version = {latest}")
        db.commit()
        return

    version = db.execute("PRAGMA user_version").fetchone()[0]
    for number, sql in steps:
        if number > version:
            db.executescript(f"BEGIN;\n{sql}\nPRAGMA user_version = {number};\nCOMMIT;")


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


@click.command("import-xlsx")
@click.argument("path", type=click.Path(exists=True, dir_okay=False))
@click.option("--dry-run", is_flag=True, help="Show what would be imported without saving.")
@click.option("--replace", is_flag=True, help="Delete the current journal and registers first, then import.")
def import_xlsx_command(path, dry_run, replace):
    """Import a stalljournal spreadsheet (the Google Sheets layout)."""
    from .importer import ImportRefused, import_workbook

    try:
        report = import_workbook(path, dry_run=dry_run, replace=replace)
    except ImportRefused as exc:
        raise click.ClickException(str(exc))
    click.echo(report)


def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
    app.cli.add_command(seed_demo_command)
    app.cli.add_command(import_xlsx_command)
    with app.app_context():
        init_db()
