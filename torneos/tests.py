from datetime import timedelta, time
from unittest.mock import patch
import pytest
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
        bye=t.partidas.get(ronda=1,orden=0); final=t.partidas.get(ronda=2)
        self.assertEqual(bye.estado,"finalizada"); self.assertEqual(bye.ganador,teams[0]); self.assertEqual(final.equipo_a,teams[0])
    def test_corregir_resultado_limpia_rondas_siguientes(self):
        t=tournament()
        for name,rut in [("A","12345678-5"),("B","11111111-1"),("C","22222222-2"),("D","33333333-3")]: team(t,name,rut)
        with patch("torneos.services.random.shuffle",lambda x:None): generar_bracket(t)
        semi1=t.partidas.get(ronda=1,orden=0); semi2=t.partidas.get(ronda=1,orden=1)
        ganador_original=semi1.equipo_a; ganador_corregido=semi1.equipo_b
        registrar_resultado(semi1,1,0); registrar_resultado(semi2,1,0)
        final=t.partidas.get(ronda=2); self.assertEqual(final.equipo_a,ganador_original); registrar_resultado(final,1,0)
        registrar_resultado(semi1,0,1,reabrir=True); final.refresh_from_db()
        self.assertIsNone(final.ganador); self.assertEqual(final.score_a,0); self.assertEqual(final.equipo_a,ganador_corregido)

def _rut_valido(numero):
    body=str(20000000+numero)
    total=sum(int(d)*factor for d,factor in zip(reversed(body),(2,3,4,5,6,7,2,3)))
    result=11-total%11
    dv="0" if result==11 else "K" if result==10 else str(result)
    return f"{body}-{dv}"

@pytest.mark.django_db
@pytest.mark.parametrize("n",[2,3,4,5,6,7,8,9,11,13,16])
def test_bracket_cualquier_tamano_llega_a_un_campeon(n):
    t=tournament(capacity=16)
    for i in range(n): team(t,f"Equipo {i+1}",_rut_valido(i))
    with patch("torneos.services.random.shuffle",lambda x:None): generar_bracket(t)
    assert not t.partidas.filter(ronda=1,equipo_a__isnull=True,equipo_b__isnull=True).exists()
    while True:
        jugables=list(t.partidas.filter(estado="pendiente",equipo_a__isnull=False,equipo_b__isnull=False))
        if not jugables: break
        for partida in jugables: registrar_resultado(partida,1,0)
    final=t.partidas.order_by("-ronda").first(); final.refresh_from_db()
    assert final.estado=="finalizada"
    assert final.ganador_id is not None

@pytest.mark.django_db
def test_nombre_equipo_duplicado_devuelve_400():
    t=tournament(); team(t,"Los Pro","12345678-5"); a=attendee("11111111-1","Dos")
    response=APIClient().post("/api/torneos/test/inscripcion/",{"nombre_equipo":"  los pro  ","integrantes":[{"rut":a.rut,"gamertag":"dos"}]},format="json")
    assert response.status_code==400
    assert response.data["nombre_equipo"] == ["El nombre ya está tomado en ese torneo, elige otro."]

@pytest.mark.django_db
def test_endpoint_admin_torneo_requiere_auth_y_cumple_contrato():
    tournament(); user=get_user_model().objects.create_user("admin")
    client=APIClient(); assert client.get("/api/admin/torneos/test/").status_code==401
    client.force_authenticate(user)
    response=client.get("/api/admin/torneos/test/")
    assert response.status_code==200
    assert set(response.data)=={"torneo","slug","estado","horario","equipos_confirmados","equipos_espera","rondas"}

@pytest.mark.django_db
def test_acreditar_y_sortear_solo_equipos_acreditados():
    t=tournament(); teams=[team(t,chr(65+i),_rut_valido(i)) for i in range(3)]
    user=get_user_model().objects.create_user("admin"); client=APIClient(); client.force_authenticate(user)
    for equipo in teams[:2]:
        response=client.patch(f"/api/admin/equipos/{equipo.pk}/",{"acreditado":True},format="json")
        assert response.status_code==200
        equipo.refresh_from_db(); assert equipo.acreditado is True; assert equipo.acreditado_en is not None
    with patch("torneos.services.random.shuffle",lambda x:None):
        response=client.post("/api/admin/torneos/test/sorteo/",{"solo_acreditados":True},format="json")
    assert response.status_code==200
    assert set(t.partidas.values_list("equipo_a_id",flat=True)) | set(t.partidas.values_list("equipo_b_id",flat=True)) >= {teams[0].pk,teams[1].pk}
    assert not t.partidas.filter(equipo_a=teams[2]).exists()
    assert not t.partidas.filter(equipo_b=teams[2]).exists()

@pytest.mark.django_db
def test_sorteo_rechaza_menos_de_dos_acreditados_con_recuento():
    t=tournament(); acreditado=team(t,"A",_rut_valido(0)); team(t,"B",_rut_valido(1)); acreditado.acreditado=True; acreditado.save()
    user=get_user_model().objects.create_user("admin"); client=APIClient(); client.force_authenticate(user)
    response=client.post("/api/admin/torneos/test/sorteo/",{"solo_acreditados":True},format="json")
    assert response.status_code==400
    assert "1 equipos acreditados de 2 inscritos" in response.data["detail"]

@pytest.mark.django_db
def test_walkover_finaliza_y_propaga_ganador():
    t=tournament()
    for i in range(4): team(t,chr(65+i),_rut_valido(i))
    with patch("torneos.services.random.shuffle",lambda x:None): generar_bracket(t)
    partida=t.partidas.get(ronda=1,orden=0); user=get_user_model().objects.create_user("admin")
    client=APIClient(); client.force_authenticate(user)
    response=client.patch(f"/api/admin/partidas/{partida.pk}/resultado/",{"walkover":"b"},format="json")
    assert response.status_code==200
    partida.refresh_from_db(); siguiente=partida.siguiente_partida; siguiente.refresh_from_db()
    assert partida.por_walkover is True
    assert (partida.score_a,partida.score_b)==(0,0)
    assert partida.ganador==partida.equipo_b
    assert siguiente.equipo_a==partida.equipo_b

@pytest.mark.django_db
def test_walkover_y_marcadores_son_excluyentes():
    t=tournament(); team(t,"A",_rut_valido(0)); team(t,"B",_rut_valido(1)); generar_bracket(t)
    partida=t.partidas.get(); user=get_user_model().objects.create_user("admin")
    client=APIClient(); client.force_authenticate(user)
    response=client.patch(f"/api/admin/partidas/{partida.pk}/resultado/",{"walkover":"a","score_a":1,"score_b":0},format="json")
    assert response.status_code==400
    partida.refresh_from_db(); assert partida.estado=="pendiente"
