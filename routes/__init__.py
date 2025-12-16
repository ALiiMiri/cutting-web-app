# Routes package initialization
# This file registers all blueprints with the Flask app

from flask import Blueprint

# Import blueprints
from .inventory import inventory_bp
from .quotes import quotes_bp

def register_blueprints(app):
    """Register all blueprints with the Flask app."""
    app.register_blueprint(inventory_bp)
    app.register_blueprint(quotes_bp)
