#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
# Este archivo es el punto de entrada de Django para tareas de administración.
# Es necesario para ejecutar comandos como runserver, migrate, createsuperuser, etc.
import os
import sys


def main():
    """Run administrative tasks."""
    # Define qué archivo de configuración (settings.py) debe cargar Django.
    # Sin esta variable, Django no sabría cómo iniciar el proyecto.
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Angie_presentacion.settings')
    try:
        # Importa el ejecutor oficial de comandos de Django.
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        # Si Django no está instalado o el entorno virtual no está activo,
        # se lanza un error claro para facilitar el diagnóstico.
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    # Ejecuta el comando recibido por terminal (por ejemplo: runserver).
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    # Evita que main() se ejecute cuando este archivo se importa como módulo.
    main()
