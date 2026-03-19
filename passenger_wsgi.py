import sys
import os

# Asegurar que Phusion Passenger encuentre los paquetes en el entorno virtual
# (El entorno lo proveerá la opción "Setup Python App" de cPanel)
sys.path.insert(0, os.path.dirname(__file__))

# Requerimos el adaptador para WSGI
from a2wsgi import ASGIMiddleware
from api import app

# Exponemos "application" como variable WSGI para que Passenger de cPanel la encuentre
application = ASGIMiddleware(app)
