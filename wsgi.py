import sys
import os

# IMPORTANT: Update this path to match your project's directory on PythonAnywhere
# It will look something like '/home/YourUsername/YourProjectFolder'
project_home = '/home/RdtwMax/AI_Projects'
if project_home not in sys.path:
    sys.path.insert(0, project_home)

# Import the Flask app object from your main script.
# The script is named Stars.py, so the module is `Stars`.
from Stars import flask_app as application