from datetime import timedelta, time
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from evento.tests import attendee
from .models import Equipo, Integrante, Partida, Torneo
from .services import generar_bracket, registrar_resultado

def tournament(capacity=4):
    return Torneo.objects.create(nombre="Test",slug="test",juego="Game",modalidad="individual",jugadores_por_equipo=1,cupo_equipos=capacity,hora_inicio=time(11),hora_fin=time(12),cierre_inscripciones=timezone.now()+timedelta(days=1))
def team(t,name,rut):
    a=attendee(rut,name); e=Equipo.objects.create(torneo=t,nombre=name,capitan=a,estado="confirmado"); Integrante.objects.create(equipo=e,asistente=a); return e

class TorneoTests(TestCase):
    def test_lista_espera_sin_cupo(self):
        t=tournament(1); team(t,"Uno","12345678-5"); a=attendee("11111111-1","Dos")
        response=APIClient().post("/api/torneos/test/inscripcion/",{"nombre_equipo":"Dos","integrantes":[{"rut":a.rut,"gamertag":"dos"}]},format="json")
        self.assertEqual(response.status_code,201); self.assertEqual(response.data["estado"],"espera"); self.assertEqual(response.data["posicion_espera"],1)
    def test_bracket_tres_equipos_propaga_bye(self):
        t=tournament(); teams=[team(t,"A","12345678-5"),team(t,"B","11111111-1"),team(t,"C","22222222-2")]
        with patch("torneos.services.random.shuffle",lambda x:None): generar_bracket(t)
        self.assertEqual(t.partidas.count(),3)
        bye=t.partidas.get(ronda=1,orden=1); final=t.partidas.get(ronda=2)
        self.assertEqual(bye.estado,"finalizada"); self.assertEqual(bye.ganador,teams[2]); self.assertEqual(final.equipo_b,teams[2])
    def test_corregir_resultado_limpia_rondas_siguientes(self):
        t=tournament(); teams=[team(t,"A","12345678-5"),team(t,"B","11111111-1"),team(t,"C","22222222-2"),team(t,"D","33333333-3")]
        with patch("torneos.services.random.shuffle",lambda x:None): generar_bracket(t)
        semi1=t.partidas.get(ronda=1,orden=0); semi2=t.partidas.get(ronda=1,orden=1)
        registrar_resultado(semi1,1,0); registrar_resultado(semi2,1,0)
        final=t.partidas.get(ronda=2); registrar_resultado(final,1,0)
        registrar_resultado(semi1,0,1); final.refresh_from_db()
        self.assertIsNone(final.ganador); self.assertEqual(final.score_a,0); self.assertEqual(final.equipo_a,teams[1])
