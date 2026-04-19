"""
WSGI config for Angie_presentacion project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

# Define el módulo de settings para servidores WSGI (gunicorn, mod_wsgi).
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Angie_presentacion.settings')

# `application` es la puerta de entrada estándar para despliegues WSGI.
application = get_wsgi_application()
