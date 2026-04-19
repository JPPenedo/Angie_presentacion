from django.db import models


class CuentaAlumno(models.Model):
    """
    Registro básico de cuentas creadas desde la interfaz de "Crear cuenta".
    """

    correo_institucional = models.EmailField(unique=True)
    nombre_completo = models.CharField(max_length=120)
    id_institucional = models.CharField(max_length=8, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.nombre_completo} ({self.correo_institucional})"
