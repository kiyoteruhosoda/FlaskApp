from flask import Flask

def create_app():
    app = Flask(__name__)

    # 各フォルダのBlueprintを登録
    from app1 import bp as app1_bp
    from app2 import bp as app2_bp

    app.register_blueprint(app1_bp)
    app.register_blueprint(app2_bp)

    @app.get("/")               # ← これが無いと / は 404
    def index():
        return "Root OK"

    return app


if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)
