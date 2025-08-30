from flask_sqlalchemy import SQLAlchemy

# Shared database instance for ORM models

db = SQLAlchemy()

__all__ = ["db"]
