from django.contrib import admin
from .models import Torneo, Equipo, Integrante, Partida
@admin.register(Torneo)
class TorneoAdmin(admin.ModelAdmin): list_display=["nombre","modalidad","cupo_equipos","estado","hora_inicio"]; search_fields=["nombre","slug","juego"]; list_filter=["modalidad","estado"]
@admin.register(Equipo)
class EquipoAdmin(admin.ModelAdmin): list_display=["nombre","torneo","capitan","estado","seed"]; search_fields=["nombre","capitan__rut"]; list_filter=["torneo","estado"]
@admin.register(Integrante)
class IntegranteAdmin(admin.ModelAdmin): list_display=["equipo","asistente","gamertag"]; search_fields=["equipo__nombre","asistente__rut","gamertag"]; list_filter=["equipo__torneo"]
@admin.register(Partida)
class PartidaAdmin(admin.ModelAdmin): list_display=["torneo","ronda","orden","equipo_a","equipo_b","ganador","estado"]; search_fields=["torneo__nombre","equipo_a__nombre","equipo_b__nombre"]; list_filter=["torneo","ronda","estado"]
