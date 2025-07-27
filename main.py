import sys
import os

# Add src to Python path so we can import from src modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from api.api import create_app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8080)
