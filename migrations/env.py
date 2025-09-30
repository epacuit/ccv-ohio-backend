# migrations/env.py
from logging.config import fileConfig
from sqlalchemy import engine_from_config
from sqlalchemy import pool
from alembic import context
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

from alembic import context
from sqlalchemy import engine_from_config, pool
import os

# Your models
from app.database import Base  # or wherever your Base is

config = context.config

# Override sqlalchemy.url with environment variable
config.set_main_option(
    'sqlalchemy.url',
    os.environ.get('DATABASE_URL', '')
)

target_metadata = Base.metadata

# ... rest of your env.py
# Add parent directory to path so we can import app
sys.path.append(str(Path(__file__).parent.parent))

# Import your models
from app.models import Base

# Load environment variables
load_dotenv()

config = context.config

# Set up logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set database URL from .env (remove +asyncpg for Alembic)
database_url = os.getenv("DATABASE_URL")
if not database_url:
    raise ValueError("DATABASE_URL not found in environment variables")

# Alembic needs sync driver, not async
database_url = database_url.replace("+asyncpg", "")
config.set_main_option("sqlalchemy.url", database_url)

# Set target metadata from your models
target_metadata = Base.metadata

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    configuration = config.get_section(config.config_ini_section)
    configuration['sqlalchemy.url'] = database_url  # Add this line
    
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()