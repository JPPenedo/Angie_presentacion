"""
ASGI config for Angie_presentacion project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/asgi/
"""

import os

from django.core.asgi import get_asgi_application

# Define el módulo de configuración que ASGI debe cargar.
# Es obligatorio para servir la app en servidores asíncronos.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Angie_presentacion.settings')

# `application` es el callable ASGI que usa el servidor (uvicorn/daphne).
application = get_asgi_application()
