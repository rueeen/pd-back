from django.core.management.base import BaseCommand
from django.utils.text import slugify
from evento.models import Area, Carrera

CATALOGO = [
    (1, "Administración", ["Administración de Empresas", "Comercio Exterior", "Ingeniería en Administración de Empresas"]),
    (2, "Gastronomía", ["Gastronomía"]),
    (3, "Turismo y Hospitalidad", ["Gestión Turística"]),
    (4, "Construcción", ["Técnico en Topografía y Geomática", "Construcción Civil", "Técnico en Construcción"]),
    (5, "Energía", ["Técnico en Electricidad Industrial"]),
    (6, "Logística", ["Técnico en Logística"]),
    (7, "Mecánica", ["Técnico en Mecánica y Electromovilidad Automotriz", "Ingeniería en Mecánica y Electromovilidad Automotriz"]),
    (8, "Automatización, Electrónica y Robótica", ["Ingeniería en Automatización y Robótica", "Técnico en Automatización y Robótica"]),
    (9, "Diseño e Industria Digital", ["Diseño Digital Profesional", "Diseño Digital y Web"]),
    (10, "Informática, Ciberseguridad y Telecomunicaciones", ["Analista Programador", "Ingeniería en Informática"]),
]

class Command(BaseCommand):
    help = "Carga o actualiza el catálogo de áreas y carreras."

    def handle(self, *args, **options):
        for orden, nombre, carreras in CATALOGO:
            area, _ = Area.objects.update_or_create(
                slug=slugify(nombre), defaults={"nombre": nombre, "orden": orden}
            )
            for carrera_nombre in carreras:
                Carrera.objects.update_or_create(
                    slug=slugify(carrera_nombre),
                    defaults={"nombre": carrera_nombre, "area": area},
                )
        self.stdout.write(self.style.SUCCESS("Áreas y carreras cargadas correctamente."))
