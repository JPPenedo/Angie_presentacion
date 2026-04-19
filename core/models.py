from django.db import models
from django.utils import timezone


class CuentaAlumno(models.Model):
    """
    Registro básico de cuentas creadas desde la interfaz de "Crear cuenta".
    """

    ROLES = (
        ("alumno", "Alumno"),
        ("docente", "Docente"),
        ("coordinacion", "Coordinación académica"),
    )

    correo_institucional = models.EmailField(unique=True)
    nombre_completo = models.CharField(max_length=120)
    id_institucional = models.CharField(max_length=8, unique=True)
    rol = models.CharField(max_length=20, choices=ROLES, default="alumno")
    password_hash = models.CharField(max_length=128, default="", blank=True)
    is_verified = models.BooleanField(default=False)
    verification_token = models.CharField(max_length=64, default="", blank=True, db_index=True)
    reset_token = models.CharField(max_length=64, default="", blank=True, db_index=True)
    reset_token_expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.nombre_completo} ({self.correo_institucional})"

    def reset_token_is_valid(self):
        return bool(
            self.reset_token
            and self.reset_token_expires_at
            and self.reset_token_expires_at > timezone.now()
        )
