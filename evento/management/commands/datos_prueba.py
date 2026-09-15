from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from evento.models import Asistente, RetiroCompleto
from evento.models import Carrera
from torneos.models import Equipo, Integrante, Torneo


EMAIL_PREFIX = "ensayo-pd+"


def rut_valido(numero):
    cuerpo = str(30000000 + numero)
    suma = sum(int(digito) * factor for digito, factor in zip(reversed(cuerpo), (2, 3, 4, 5, 6, 7, 2, 3)))
    resultado = 11 - suma % 11
    dv = "0" if resultado == 11 else "K" if resultado == 10 else str(resultado)
    return f"{cuerpo}-{dv}"


class Command(BaseCommand):
    help = "Genera o limpia asistentes y equipos reconocibles para el ensayo general."

    def add_arguments(self, parser):
        parser.add_argument("--asistentes", type=int, default=60)
        parser.add_argument("--equipos", type=int, default=6)
        parser.add_argument("--limpiar", action="store_true")
        parser.add_argument("--forzar", action="store_true")

    def handle(self, *args, **options):
        if options["limpiar"]:
            return self._limpiar(options["forzar"])
        if options["asistentes"] < 1 or options["equipos"] < 0:
            raise CommandError("Las cantidades deben ser positivas.")
        return self._generar(options["asistentes"], options["equipos"])

    @transaction.atomic
    def _generar(self, cantidad_asistentes, cantidad_equipos):
        carreras = list(Carrera.objects.filter(activa=True).select_related("area"))
        torneos = list(Torneo.objects.all().order_by("pk"))
        if not carreras:
            raise CommandError("No hay carreras. Ejecute cargar_carreras primero.")
        if cantidad_equipos and len(torneos) < 3:
            raise CommandError("Deben estar cargados los tres torneos.")

        asistentes = []
        for indice in range(cantidad_asistentes):
            carrera = carreras[indice % len(carreras)]
            asistente, _ = Asistente.objects.update_or_create(
                email=f"{EMAIL_PREFIX}{indice + 1:03d}@example.test",
                defaults={
                    "nombre": f"Prueba {indice + 1:03d}", "apellido": "Ensayo General",
                    "rut": rut_valido(indice), "tipo": "estudiante", "area": carrera.area,
                    "carrera": carrera, "aporte": Asistente.APORTES[indice % len(Asistente.APORTES)][0],
                },
            )
            asistentes.append(asistente)

        cursor = 0
        for indice in range(cantidad_equipos):
            torneo = torneos[indice % 3]
            if torneo.jugadores_por_equipo > cantidad_asistentes:
                raise CommandError("No hay suficientes asistentes para formar los equipos solicitados.")
            miembros = [asistentes[(cursor + offset) % len(asistentes)] for offset in range(torneo.jugadores_por_equipo)]
            cursor += torneo.jugadores_por_equipo
            equipo, _ = Equipo.objects.update_or_create(
                torneo=torneo, nombre=f"ENSAYO-{indice + 1:02d}",
                defaults={"capitan": miembros[0], "estado": "confirmado"},
            )
            equipo.integrantes.all().delete()
            Integrante.objects.bulk_create([
                Integrante(equipo=equipo, asistente=miembro, gamertag=f"test-{miembro.pk}")
                for miembro in miembros
            ])
        self.stdout.write(self.style.SUCCESS(f"Creados {cantidad_asistentes} asistentes y {cantidad_equipos} equipos de prueba."))

    @transaction.atomic
    def _limpiar(self, forzar):
        if not settings.DEBUG and not forzar:
            raise CommandError("La limpieza está deshabilitada con DEBUG=False. Use --forzar solo si verificó la base de datos.")
        confirmacion = input('Escriba "BORRAR" para eliminar los datos del ensayo: ')
        if confirmacion != "BORRAR":
            raise CommandError("Limpieza cancelada.")
        asistentes = Asistente.objects.filter(email__startswith=EMAIL_PREFIX)
        ids = list(asistentes.values_list("pk", flat=True))
        equipos = Equipo.objects.filter(capitan_id__in=ids) | Equipo.objects.filter(integrantes__asistente_id__in=ids)
        equipos.distinct().delete()
        RetiroCompleto.objects.filter(asistente_id__in=ids).delete()
        eliminados = asistentes.delete()[0]
        self.stdout.write(self.style.SUCCESS(f"Datos de prueba eliminados ({eliminados} registros relacionados)."))
