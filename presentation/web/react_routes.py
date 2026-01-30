from flask import Flask, render_template, send_from_directory
import os

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
        # Only serve specific static files, not catch-all
        static_files = ['favicon.ico', 'manifest.json', 'logo192.png', 'robots.txt', 'vite.svg']
        if filename in static_files:
            build_path = os.path.join(app.root_path, '..', '..', 'frontend', 'build')
            try:
                return send_from_directory(build_path, filename)
            except FileNotFoundError:
                app.logger.debug(f"Static file not found: {filename}")
                return {'error': 'File not found'}, 404
        # Return 404 if not a static file
        app.logger.debug(f"Not a static file: {filename}")
        return {'error': 'File not found'}, 404
    
    # Serve React app for all non-API routes (catch-all must be last)
    @app.route('/', defaults={'path': ''})
    @app.route('/<path:path>')
    def catch_all(path):
        # Skip static files - they are handled by specific routes above
        static_files = ['favicon.ico', 'manifest.json', 'logo192.png', 'robots.txt', 'vite.svg']
        if path in static_files:
            return react_static(path)
            
        # API routes should not be caught by React
        if path.startswith('api/'):
            return {'error': 'API endpoint not found'}, 404
            
        # Assets routes should not be caught by React (handled by react_assets)
        if path.startswith('assets/'):
            return {'error': 'Asset not found'}, 404
            
        # Health check routes should not be caught by React
        if path.startswith('health/'):
            return {'error': 'Health endpoint not found'}, 404
            
        # Admin routes should serve React app
        # Auth routes should serve React app
        # All other routes should serve React app
        
        # Production: serve from build directory
        build_path = os.path.join(app.root_path, '..', '..', 'frontend', 'build')
        index_path = os.path.join(build_path, 'index.html')
        
        app.logger.debug(f"Looking for React build at: {build_path}")
        app.logger.debug(f"Index path: {index_path}")
        app.logger.debug(f"Index exists: {os.path.exists(index_path)}")
        
        if os.path.exists(index_path):
            return send_from_directory(build_path, 'index.html')
        else:
            # Build not found - in development, direct user to Vite
            return f'''
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
            ''', 2