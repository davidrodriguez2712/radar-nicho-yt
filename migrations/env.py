from alembic import context

from nicheradar.config import Settings
from nicheradar.repositories.database import database_engine
from nicheradar.repositories.schema import metadata

if context.is_offline_mode():
    context.configure(
        url="postgresql+psycopg://",
        target_metadata=metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    supplied = context.config.attributes.get("connection")
    if supplied is not None:
        context.configure(connection=supplied, target_metadata=metadata)
        with context.begin_transaction():
            context.run_migrations()
    else:
        engine = database_engine(Settings())
        try:
            with engine.connect() as connection:
                context.configure(connection=connection, target_metadata=metadata)
                with context.begin_transaction():
                    context.run_migrations()
        finally:
            engine.dispose()
