from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    path('',                     views.dashboard,      name='dashboard'),
    path('grupo/<int:grupo_id>/', views.detalle_grupo,  name='detalle_grupo'),
    path('login/',               views.login_view,     name='login'),
    path('logout/',              views.logout_view,    name='logout'),
    path('mi-perfil/',           views.perfil_alumno,  name='perfil_alumno'),
]
