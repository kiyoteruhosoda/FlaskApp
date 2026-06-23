from flask import Flask, current_app, send_from_directory
import os

# Static files that are served from the React build root rather than being
# treated as client-side routes.
_STATIC_FILES = ['favicon.ico', 'manifest.json', 'logo192.png', 'robots.txt', 'vite.svg']


def _react_build_path() -> str:
    return os.path.join(current_app.root_path, '..', '..', 'frontend', 'build')


def serve_react_app(path: str = ''):
    """Serve the React single-page application shell for *path*.

    Client-side routes (``/login``, ``/dashboard`` …) all resolve to the same
    ``index.html`` so that the front-end router can take over.  API, asset and
    health prefixes are explicitly excluded so they keep returning their own
    responses instead of the SPA shell.
    """

    # Static files are handled by their dedicated route.
    if path in _STATIC_FILES:
        return serve_react_static(path)

    # These prefixes must never be swallowed by the SPA catch-all.
    if path.startswith('api/'):
        return {'error': 'API endpoint not found'}, 404
    if path.startswith('assets/'):
        return {'error': 'Asset not found'}, 404
    if path.startswith('health/'):
        return {'error': 'Health endpoint not found'}, 404

    build_path = _react_build_path()
    index_path = os.path.join(build_path, 'index.html')

    if os.path.exists(index_path):
        return send_from_directory(build_path, 'index.html')

    # Build not found - in development, direct user to Vite
    return '''
    <!DOCTYPE html>
    <html>
    <head><title>PhotoNest - Development Mode</title></head>
    <body>
        <h1>PhotoNest - Development Mode</h1>
        <p>React build not found. Please access the Vite dev server directly:</p>
        <p><a href="http://localhost:3000">http://localhost:3000</a></p>
        <pre>cd frontend && npm run dev</pre>
        <hr>
        <p>For production, build first:</p>
        <pre>cd frontend && npm run build</pre>
    </body>
    </html>
    ''', 200


def serve_react_static(filename: str):
    """Serve a known static asset from the React build root."""
    if filename in _STATIC_FILES:
        build_path = _react_build_path()
        try:
            return send_from_directory(build_path, filename)
        except FileNotFoundError:
            current_app.logger.debug(f"Static file not found: {filename}")
            return {'error': 'File not found'}, 404
    # Not a known static asset: serve the React app so that client-side
    # routes such as /login or /reset-password resolve correctly.
    return serve_react_app(filename)


def register_react_routes(app: Flask):
    """Register routes for serving React application."""

    # Serve static assets from React build (Vite uses /assets instead of /static)
    @app.route('/assets/<path:filename>')
    def react_assets(filename):
        build_path = os.path.join(app.root_path, '..', '..', 'frontend', 'build', 'assets')
        return send_from_directory(build_path, filename)

    # Also serve other static files (favicon, manifest, etc)
    @app.route('/<path:filename>')
    def react_static(filename):
        return serve_react_static(filename)

    # Serve the React app at the site root. This is named "index" because
    # server-rendered templates (e.g. base.html navbar) link back here via
    # url_for("index").
    @app.route('/')
    def index():
        return serve_react_app('')

    # Serve React app for all non-API routes (catch-all must be last)
    @app.route('/<path:path>')
    def catch_all(path):
        return serve_react_app(path)
