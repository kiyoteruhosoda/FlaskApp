from webapp import create_app
from core.lifecycle_logging import register_lifecycle_logging

app = create_app()

if __name__ == "__main__":
    register_lifecycle_logging(app)
    app.run(debug=True)
