# app/__init__.py
from flask import Flask
from .config import Config
from .services.catalogue import init_catalogue

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    
    # Register blueprints
    from .routes import main_bp
    app.register_blueprint(main_bp)
    
    # Initialize services
    with app.app_context():
        init_catalogue()
    
    return app