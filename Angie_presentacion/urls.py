"""
URL configuration for Angie_presentacion project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include

# Tabla principal de rutas del proyecto.
# Centraliza la entrada al admin de Django y delega el resto a la app `core`.
# Profesor: este archivo es el "router raíz"; rara vez contiene lógica de negocio.
urlpatterns = [
    # Ruta interna de administración automática de Django.
    path('admin/', admin.site.urls),
    # Todas las páginas funcionales del sistema viven dentro de `core.urls`.
    path('', include('core.urls')),
]
