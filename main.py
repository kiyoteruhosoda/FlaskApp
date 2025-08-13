from webapp import create_app

app = create_app()

@app.get("/")               # ← これが無いと / は 404
def index():
    return "Root OK"

if __name__ == '__main__':
    app.run(debug=True)
