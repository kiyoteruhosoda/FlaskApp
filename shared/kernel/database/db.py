from flask_sqlalchemy import SQLAlchemy

# Shared database instance for ORM models

db = SQLAlchemy(session_options={"expire_on_commit": False})

__all__ = ["db"]
