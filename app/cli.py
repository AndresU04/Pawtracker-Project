import click
from flask.cli import with_appcontext

from .extensions import db


@click.command("init-db")
@click.option("--reset", is_flag=True, help="Drop all tables first (destroys data).")
@with_appcontext
def init_db_command(reset):
    """Create database tables."""
    if reset:
        db.drop_all()
    db.create_all()
    click.echo("Database tables created.")


@click.command("seed-db")
@with_appcontext
def seed_db_command():
    """Load sample data (idempotent: skips if data already exists)."""
    from .seed import seed

    created = seed()
    click.echo("Sample data loaded." if created else "Database already has data; nothing seeded.")


def register_cli(app):
    app.cli.add_command(init_db_command)
    app.cli.add_command(seed_db_command)
