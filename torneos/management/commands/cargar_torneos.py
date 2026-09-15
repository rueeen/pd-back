from datetime import datetime, time
from django.core.management.base import BaseCommand
from django.utils import timezone
from torneos.models import Torneo
class Command(BaseCommand):
    help="Carga o actualiza los torneos del Día del Programador 2026."
    def handle(self,*args,**options):
        close=timezone.make_aware(datetime(2026,10,1,10,0))
        data=[
          ("mario-kart","Mario Kart 8 Deluxe","Mario Kart 8 Deluxe","individual",1,16,"bloque-1","consola",time(11),time(12,10),"Eliminación directa uno contra uno, al mejor de tres carreras. Circuitos elegidos al azar, 150cc, objetos activados. Dos estaciones en paralelo. Si una carrera se interrumpe por un problema técnico, se repite completa."),
          ("valorant","VALORANT","VALORANT","equipo",5,4,"bloque-1","pc",time(11),time(12,10),"Eliminación directa, modo partida rápida, tope de 20 minutos por partida. Dos semifinales en paralelo y una final."),
          ("smash","Super Smash Bros. Ultimate","Super Smash Bros. Ultimate","individual",1,24,"bloque-2","consola",time(13,10),time(14,25),"Eliminación directa 1v1, tres vidas, límite de 7 minutos por combate; al cumplirse el tiempo gana quien conserve más vidas. Dos estaciones en paralelo."),
          ("lol-aram","League of Legends (ARAM)","League of Legends","equipo",5,4,"bloque-2","pc",time(13,10),time(14,25),"Sala personalizada, gana la primera escuadra en conseguir 5 bajas. Cada llave al mejor de 3, tope de 10 minutos por partida. El coordinador verifica el marcador y declara el resultado."),
        ]
        for slug,name,game,mode,size,capacity,block,equipment,start,end,rules in data:
            Torneo.objects.update_or_create(slug=slug,defaults={"nombre":name,"juego":game,"modalidad":mode,"jugadores_por_equipo":size,"cupo_equipos":capacity,"bloque":block,"equipamiento":equipment,"hora_inicio":start,"hora_fin":end,"reglas":rules,"cierre_inscripciones":close})
        self.stdout.write(self.style.SUCCESS("Torneos cargados correctamente."))
