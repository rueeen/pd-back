from datetime import datetime, time
from django.core.management.base import BaseCommand
from django.utils import timezone
from torneos.models import Torneo
class Command(BaseCommand):
    help="Carga o actualiza los torneos del Día del Programador 2026."
    def handle(self,*args,**options):
        close=timezone.make_aware(datetime(2026,10,1,10,0))
        data=[
          ("mario-kart","Mario Kart 8 Deluxe","Mario Kart 8 Deluxe","individual",1,16,"bloque-1","consola",time(11),time(12,30),"Eliminación directa uno contra uno, al mejor de tres carreras. La final se juega al mejor de cinco. Circuitos elegidos al azar, 150cc, objetos activados. Dos estaciones en paralelo. Si una carrera se interrumpe por un problema técnico, se repite completa."),
          ("valorant","VALORANT","VALORANT","equipo",5,4,"bloque-1","pc",time(11),time(12,30),"Eliminación directa. Modo de partida rápida, con tope de 25 minutos por partida. Las semifinales se juegan a una partida y la final al mejor de tres. Dos semifinales en paralelo."),
          ("smash","Super Smash Bros. Ultimate","Super Smash Bros. Ultimate","individual",1,24,"bloque-2","consola",time(13),time(14,45),"Eliminación directa uno contra uno. Tres vidas con límite de 7 minutos por combate; al cumplirse el tiempo gana quien conserve más vidas. Las semifinales y la final se juegan al mejor de tres combates. Dos estaciones en paralelo."),
          ("lol-aram","League of Legends (ARAM)","League of Legends","equipo",5,4,"bloque-2","pc",time(13),time(14,45),"Eliminación directa en sala personalizada. Gana la partida la primera escuadra que consiga 5 bajas, con tope de 10 minutos por partida. Las llaves se definen al mejor de tres y la final al mejor de cinco. El coordinador verifica el marcador y declara el resultado. Dos semifinales en paralelo."),
        ]
        for slug,name,game,mode,size,capacity,block,equipment,start,end,rules in data:
            defaults={"nombre":name,"juego":game,"modalidad":mode,"jugadores_por_equipo":size,"bloque":block,"equipamiento":equipment,"hora_inicio":start,"hora_fin":end,"reglas":rules,"cierre_inscripciones":close}
            Torneo.objects.update_or_create(slug=slug,defaults=defaults,create_defaults={**defaults,"cupo_equipos":capacity})
        self.stdout.write(self.style.SUCCESS("Torneos cargados correctamente."))
