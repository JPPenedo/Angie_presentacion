from django.urls import path
from . import views

# Profesor: `app_name` crea un namespace para evitar conflictos de nombres entre apps.
# Ejemplo: `core:login` deja claro que la ruta pertenece a esta app.
app_name = 'core'

# Enrutador local de la app.
# Define qué vista responde a cada URL del módulo académico.
# Profesor: lee este bloque como "mapa URL -> función Python".
urlpatterns = [
    # Home del sistema para docente autenticado.
    path('',                     views.dashboard,      name='dashboard'),
    # Detalle de un grupo específico usando su id numérico.
    path('grupo/<int:grupo_id>/', views.detalle_grupo,  name='detalle_grupo'),
    # Pantalla de acceso al sistema.
    path('login/',               views.login_view,     name='login'),
    # Cierre de sesión y limpieza de datos de autenticación.
    path('logout/',              views.logout_view,    name='logout'),
    # Vista principal del alumno (perfil académico).
    path('mi-perfil/',           views.perfil_alumno,  name='perfil_alumno'),
]
