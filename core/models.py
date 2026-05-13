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
        ("director", "Dirección / Administración"),
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
    cap_subido_en = models.DateTimeField(null=True, blank=True)
    cap_nombre_archivo = models.CharField(max_length=260, default="", blank=True)
    cap_texto_extraido = models.TextField(blank=True)
    cap_error_lectura = models.CharField(max_length=500, blank=True)
    cap_extraccion_resumen = models.CharField(
        max_length=240,
        blank=True,
        help_text="Motor elegido y estadísticas de la última lectura local del CAP.",
    )
    cap_estructurado = models.JSONField(
        default=dict,
        blank=True,
        help_text="Parseo estructurado (program_summary, áreas, cursos) desde CAP PDF.",
    )
    cap_ultima_lectura_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.nombre_completo} ({self.id_institucional})"

    def reset_token_is_valid(self):
        return bool(
            self.reset_token
            and self.reset_token_expires_at
            and self.reset_token_expires_at > timezone.now()
        )


class EsquemaEvaluacionMateria(models.Model):
    """Esquema tipo syllabus: criterios y porcentajes por materia y periodo."""

    cuenta = models.ForeignKey(
        CuentaAlumno,
        on_delete=models.CASCADE,
        related_name="esquemas_evaluacion",
    )
    nombre_materia = models.CharField(max_length=200)
    periodo = models.CharField(max_length=120, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-actualizado_en"]
        verbose_name = "Esquema de evaluación"
        verbose_name_plural = "Esquemas de evaluación"

    def __str__(self):
        return f"{self.nombre_materia} ({self.cuenta.id_institucional})"


class BloqueEvaluacion(models.Model):
    """Grupo lateral (ej. Parciales 60 %)."""

    esquema = models.ForeignKey(
        EsquemaEvaluacionMateria,
        on_delete=models.CASCADE,
        related_name="bloques",
    )
    etiqueta_grupo = models.CharField(max_length=120)
    orden = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["orden", "id"]


class RubroEvaluacion(models.Model):
    """Fila: criterio + porcentaje como en el syllabus."""

    bloque = models.ForeignKey(
        BloqueEvaluacion,
        on_delete=models.CASCADE,
        related_name="rubros",
    )
    nombre_criterio = models.CharField(max_length=400)
    porcentaje = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    destacado = models.BooleanField(default=False)
    es_fila_total = models.BooleanField(default=False)
    orden = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["orden", "id"]


class CapLectura(models.Model):
    """Historial de subidas y lecturas del CAP."""

    cuenta = models.ForeignKey(
        CuentaAlumno,
        on_delete=models.CASCADE,
        related_name="cap_lecturas",
    )
    nombre_archivo = models.CharField(max_length=260)
    texto_extraido = models.TextField(blank=True)
    error_lectura = models.CharField(max_length=500, blank=True)
    extraccion_resumen = models.CharField(max_length=240, blank=True)
    subido_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-subido_en"]
