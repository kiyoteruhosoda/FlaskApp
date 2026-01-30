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
        static_files = ['favicon.ico', 'manifest.json', 'logo192.png', 'robots.txt']
        if filename in static_files:
            build_path = os.path.join(app.root_path, '..', '..', 'frontend', 'build')
            return send_from_directory(build_path, filename)
    
    # Serve React app for all non-API routes (catch-all must be last)
    @app.route('/', defaults={'path': ''})
    @app.route('/<path:path>')
    def catch_all(path):
        # Skip static files - they are handled by specific routes above
        static_files = ['favicon.ico', 'manifest.json', 'logo192.png', 'robots.txt']
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
        
        build_path = os.path.join(app.root_path, '..', '..', 'frontend', 'build')
        index_path = os.path.join(build_path, 'index.html')
        
        print(f"Looking for React build at: {build_path}")
        print(f"Index path: {index_path}")
        print(f"Index exists: {os.path.exists(index_path)}")
        
        if os.path.exists(index_path):
            return send_from_directory(build_path, 'index.html')
        else:
            # Fallback template if React build doesn't exist
            return render_template('react_fallback.html'), 200