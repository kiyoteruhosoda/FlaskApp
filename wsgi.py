from webapp import create_app
from core.lifecycle_logging import register_lifecycle_logging

app = create_app()
register_lifecycle_logging(app)

if __name__ == "__main__":
    app.run(debug=True)
