from django.core.management.base import BaseCommand

from core.models import CuentaAlumno


class Command(BaseCommand):
    help = (
        'Elimina filas de CuentaAlumno en la base de datos que está usando esta instancia de Django.\n'
        'Por defecto conserva rol=director. Usa --all para borrar también directores en BD. '
        'Los accesos demo (90000002, 26000000, etc.) viven en código, no aquí.\n\n'
        'IMPORTANTE: En Railway debes ejecutar: railway run python manage.py limpiar_cuentas'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--all',
            action='store_true',
            help='Elimina todas las cuentas, incluidas las de rol director en la BD.',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Solo muestra cuántas filas se borrarían, sin borrar.',
        )

    def handle(self, *args, **options):
        if options['all']:
            qs = CuentaAlumno.objects.all()
            modo = 'todas las cuentas'
        else:
            qs = CuentaAlumno.objects.exclude(rol='director')
            modo = 'cuentas excepto rol=director'

        n = qs.count()
        if options['dry_run']:
            self.stdout.write(
                self.style.WARNING(
                    f'[dry-run] Se eliminarían {n} fila(s) ({modo}). '
                    f'Total en tabla: {CuentaAlumno.objects.count()}.'
                )
            )
            return

        qs.delete()
        self.stdout.write(
            self.style.SUCCESS(
                f'Eliminadas {n} cuenta(s) ({modo}). '
                f'Restantes en tabla: {CuentaAlumno.objects.count()}.'
            )
        )
