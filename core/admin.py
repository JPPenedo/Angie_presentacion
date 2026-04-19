from django.contrib import admin
from .models import CuentaAlumno


@admin.register(CuentaAlumno)
class CuentaAlumnoAdmin(admin.ModelAdmin):
    list_display = ("nombre_completo", "correo_institucional", "id_institucional", "created_at")
    search_fields = ("nombre_completo", "correo_institucional", "id_institucional")
