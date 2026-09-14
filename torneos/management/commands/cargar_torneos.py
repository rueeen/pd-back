from datetime import datetime, time
from django.core.management.base import BaseCommand
from django.utils import timezone
from torneos.models import Torneo
class Command(BaseCommand):
    help="Carga o actualiza los torneos del Día del Programador 2026."
    def handle(self,*args,**options):
        close=timezone.make_aware(datetime(2026,10,1,11,0))
        data=[
          ("smash","Super Smash Bros. Ultimate","Super Smash Bros. Ultimate","individual",1,16,time(11,15),time(12,10),"Eliminación directa 1v1, tres vidas, límite de 7 minutos por combate; al cumplirse el tiempo gana quien conserve más vidas. Dos estaciones en paralelo."),
          ("valorant","VALORANT","VALORANT","equipo",5,4,time(12,55),time(14,5),"Eliminación directa, modo partida rápida, tope de 20 minutos por partida. Dos semifinales en paralelo y una final."),
          ("lol-aram","League of Legends (ARAM)","League of Legends","equipo",5,4,time(14,5),time(15,10),"Sala personalizada, gana la primera escuadra en conseguir 5 bajas. Cada llave al mejor de 3, tope de 10 minutos por partida. El coordinador verifica el marcador y declara el resultado."),
        ]
        for slug,name,game,mode,size,capacity,start,end,rules in data:
            Torneo.objects.update_or_create(slug=slug,defaults={"nombre":name,"juego":game,"modalidad":mode,"jugadores_por_equipo":size,"cupo_equipos":capacity,"hora_inicio":start,"hora_fin":end,"reglas":rules,"cierre_inscripciones":close})
        self.stdout.write(self.style.SUCCESS("Torneos cargados correctamente."))
