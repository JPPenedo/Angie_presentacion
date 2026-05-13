from django.contrib import admin

from .models import (
    BloqueEvaluacion,
    CapLectura,
    CuentaAlumno,
    EsquemaEvaluacionMateria,
    RubroEvaluacion,
)

admin.site.register(EsquemaEvaluacionMateria)
admin.site.register(BloqueEvaluacion)
admin.site.register(RubroEvaluacion)
admin.site.register(CapLectura)


@admin.register(CuentaAlumno)
class CuentaAlumnoAdmin(admin.ModelAdmin):
    list_display = ("nombre_completo", "id_institucional", "rol", "is_verified", "created_at")
    search_fields = ("nombre_completo", "id_institucional")
    readonly_fields = ("created_at", "reset_token_expires_at")
