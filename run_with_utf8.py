# -*- coding: utf-8 -*-
"""
Startup script that ensures UTF-8 encoding before running Flask app
"""
import sys
import os
import io

# Set UTF-8 encoding for Windows
if sys.platform == 'win32':
    # Set environment variables
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    os.environ['PYTHONUTF8'] = '1'
    
    # Try to reconfigure stdout/stderr
    try:
        if hasattr(sys.stdout, 'buffer'):
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        if hasattr(sys.stderr, 'buffer'):
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):
        # If reconfiguration fails, continue anyway
        pass

# Now import and run the Flask app
if __name__ == "__main__":
    from cutting_web_app import app
    app.run(debug=True, host='0.0.0.0', port=5000, use_reloader=False)
