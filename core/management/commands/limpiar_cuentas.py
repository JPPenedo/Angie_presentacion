from django.core.management.base import BaseCommand

from core.models import CuentaAlumno


class Command(BaseCommand):
    help = (
        'Elimina todas las cuentas de core excepto las de rol director '
        '(inicio limpio en base de datos). Usuario demo 26000000 vive en código, no aquí.'
    )

    def handle(self, *args, **options):
        qs = CuentaAlumno.objects.exclude(rol='director')
        n = qs.count()
        qs.delete()
        self.stdout.write(self.style.SUCCESS(f'Eliminadas {n} cuentas (se conservaron rol=director).'))
