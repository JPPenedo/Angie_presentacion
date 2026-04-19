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
    # Pantalla para registro de una nueva cuenta de alumno.
    path('crear-cuenta/',        views.crear_cuenta_view, name='crear_cuenta'),
    # Verificación de correo mediante token.
    path('verificar-cuenta/<str:token>/', views.verificar_cuenta_view, name='verificar_cuenta'),
    # Solicitud de recuperación por correo.
    path('recuperar-password/', views.recuperar_password_view, name='recuperar_password'),
    # Pantalla para establecer nueva contraseña con token.
    path('reset-password/<str:token>/', views.reset_password_view, name='reset_password'),
    # Cierre de sesión y limpieza de datos de autenticación.
    path('logout/',              views.logout_view,    name='logout'),
    # Vista principal del alumno (perfil académico).
    path('mi-perfil/',           views.perfil_alumno,  name='perfil_alumno'),
]
