from django.conf import settings
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
    # Página de exposición con slides actuariales y demo simplificada.
    path('expo-actuaria/', views.expo_actuaria_view, name='expo_actuaria'),
    # Página pedagógica sobre opciones: Bull Call Spread y Bear Put Spread.
    path('expo-opciones/', views.expo_opciones_view, name='expo_opciones'),
    # Posiciones sintéticas: larga (bull) y corta (bear) con call y put al mismo strike.
    path('expo-sinteticos/', views.expo_sinteticos_view, name='expo_sinteticos'),
    # Proyecto de transformación social (ODS 16): landing page informativa.
    path('proyecto-ods16/', views.proyecto_ods16_view, name='proyecto_ods16'),
    # Misma vista; URL pensada para producción: dominio (Railway) + este segmento.
    # Por defecto: /denuncia-verde/ (slug del nombre del proyecto en contexto de la vista).
    path(
        f'{settings.PROYECTO_RSOCIAL_URL_PATH}/',
        views.proyecto_ods16_view,
        name='denuncia_verde',
    ),
    # Cierre de sesión y limpieza de datos de autenticación.
    path('logout/',              views.logout_view,    name='logout'),
    path('panel-director/',      views.panel_director, name='panel_director'),
    path('mi-perfil/subir-cap/', views.subir_cap_alumno, name='subir_cap'),
    path(
        'mi-perfil/esquemas-evaluacion/nueva/',
        views.esquema_evaluacion_nuevo,
        name='esquema_evaluacion_nuevo',
    ),
    path(
        'mi-perfil/esquemas-evaluacion/<int:pk>/editar/',
        views.esquema_evaluacion_editar,
        name='esquema_evaluacion_editar',
    ),
    path(
        'mi-perfil/esquemas-evaluacion/<int:pk>/eliminar/',
        views.esquema_evaluacion_eliminar,
        name='esquema_evaluacion_eliminar',
    ),
    path(
        'mi-perfil/esquemas-evaluacion/',
        views.esquemas_evaluacion_lista,
        name='esquemas_evaluacion_lista',
    ),
    path('mi-perfil/',           views.perfil_alumno,  name='perfil_alumno'),
]
