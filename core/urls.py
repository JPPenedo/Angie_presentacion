from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('grupo/<int:grupo_id>/', views.detalle_grupo, name='detalle_grupo'),
]
