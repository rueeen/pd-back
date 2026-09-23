from datetime import datetime, timedelta, time
from unittest.mock import patch
import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from evento.tests import attendee
from evento.serializers import PaseSerializer
from .models import CambioIntegrante, Equipo, Integrante, Partida, Torneo
from .services import generar_bracket, registrar_resultado

def tournament(capacity=4):
    return Torneo.objects.create(nombre="Test",slug="test",juego="Game",modalidad="individual",jugadores_por_equipo=1,cupo_equipos=capacity,hora_inicio=time(11),hora_fin=time(12),cierre_inscripciones=timezone.now()+timedelta(days=1))
def team(t,name,rut):
    a=attendee(rut,name); e=Equipo.objects.create(torneo=t,nombre=name,capitan=a,estado="confirmado"); Integrante.objects.create(equipo=e,asistente=a); return e

class TorneoTests(TestCase):
    def _admin(self):
        client=APIClient(); client.force_authenticate(get_user_model().objects.create_user("config-admin")); return client

    def test_aumentar_cupo_promueve_lista_de_espera_en_orden(self):
        t=tournament(1); team(t,"A",_rut_valido(0)); primero=team(t,"B",_rut_valido(1)); segundo=team(t,"C",_rut_valido(2))
        Equipo.objects.filter(pk__in=[primero.pk,segundo.pk]).update(estado="espera")
        response=self._admin().patch("/api/admin/torneos/test/",{"cupo_equipos":2},format="json")
        primero.refresh_from_db(); segundo.refresh_from_db()
        self.assertEqual(response.status_code,200); self.assertEqual(response.data["equipos_promovidos"],[{"id":primero.pk,"nombre":"B","capitan":"B Lovelace"}])
        self.assertEqual(primero.estado,"confirmado"); self.assertEqual(segundo.estado,"espera")

    def test_reducir_cupo_bajo_confirmados_es_rechazado(self):
        t=tournament(3); team(t,"A",_rut_valido(0)); team(t,"B",_rut_valido(1))
        response=self._admin().patch("/api/admin/torneos/test/",{"cupo_equipos":1},format="json")
        self.assertEqual(response.status_code,400); self.assertIn("mayor al cupo actual",response.data["detail"])

    def test_cambiar_cupo_con_llave_publicada_es_rechazado(self):
        t=tournament(); t.estado="sorteado"; t.llave_publicada=True; t.save()
        response=self._admin().patch("/api/admin/torneos/test/",{"cupo_equipos":5},format="json")
        self.assertEqual(response.status_code,400); self.assertIn("solo puede ampliarse",response.data["detail"])

    def test_lista_espera_sin_cupo(self):
        t=tournament(1); team(t,"Uno","12345678-5"); a=attendee("11111111-1","Dos")
        response=APIClient().post("/api/torneos/test/inscripcion/",{"nombre_equipo":"Dos","integrantes":[{"rut":a.rut,"gamertag":"dos"}]},format="json")
        self.assertEqual(response.status_code,201); self.assertEqual(response.data["estado"],"espera"); self.assertEqual(response.data["posicion_espera"],1)

    def test_sorteo_exige_cerrar_inscripciones(self):
        t=tournament(); team(t,"A",_rut_valido(0)); team(t,"B",_rut_valido(1)); client=self._admin()
        response=client.post("/api/admin/torneos/test/sorteo/",{},format="json")
        self.assertEqual(response.status_code,400); self.assertIn("cerrar las inscripciones",response.data["detail"])
        self.assertEqual(client.post("/api/admin/torneos/test/cerrar-inscripciones/").status_code,200)
        response=client.post("/api/admin/torneos/test/sorteo/",{},format="json")
        self.assertEqual(response.status_code,200); self.assertEqual(response.data["estado"],"sorteado")

    def test_reabrir_torneo_sorteado_exige_despublicar_llave(self):
        t=tournament(); team(t,"A",_rut_valido(0)); team(t,"B",_rut_valido(1)); client=self._admin()
        client.post("/api/admin/torneos/test/cerrar-inscripciones/")
        client.post("/api/admin/torneos/test/sorteo/",{},format="json")
        response=client.post("/api/admin/torneos/test/reabrir-inscripciones/")
        self.assertEqual(response.status_code,400); self.assertIn("despublicar la llave",response.data["detail"])

    def test_ampliar_cupo_con_torneo_cerrado_es_rechazado(self):
        t=tournament(); t.estado="cerrado"; t.save(update_fields=["estado"])
        response=self._admin().patch("/api/admin/torneos/test/",{"cupo_equipos":5},format="json")
        self.assertEqual(response.status_code,400); self.assertIn("inscripción",response.data["detail"])

    def test_inscripcion_detecta_conflictos_solo_en_el_mismo_bloque(self):
        t=tournament(); t.bloque="bloque-1"; t.save(update_fields=["bloque"])
        participante=attendee(_rut_valido(0),"Ada"); existente=Equipo.objects.create(torneo=t,nombre="Original",capitan=participante,estado="confirmado")
        Integrante.objects.create(equipo=existente,asistente=participante)
        mismo=Torneo.objects.create(nombre="Mismo bloque",slug="mismo",juego="Game",modalidad="individual",jugadores_por_equipo=1,cupo_equipos=4,bloque="bloque-1",hora_inicio=time(11),hora_fin=time(12),cierre_inscripciones=timezone.now()+timedelta(days=1))
        otro=Torneo.objects.create(nombre="Otro bloque",slug="otro",juego="Game",modalidad="individual",jugadores_por_equipo=1,cupo_equipos=4,bloque="bloque-2",hora_inicio=time(12),hora_fin=time(13),cierre_inscripciones=timezone.now()+timedelta(days=1))
        payload={"nombre_equipo":"Nuevo","integrantes":[{"rut":participante.rut}]}
        response=APIClient().post("/api/torneos/mismo/inscripcion/",payload,format="json")
        self.assertEqual(response.status_code,400); self.assertIn("Test",str(response.data)); self.assertIn(participante.rut,str(response.data))
        response=APIClient().post("/api/torneos/otro/inscripcion/",payload,format="json")
        self.assertEqual(response.status_code,201)

    def test_advertencia_suma_pc_del_bloque_y_excluye_consolas(self):
        t=tournament(2); t.bloque="bloque-1"; t.equipamiento="pc"; t.modalidad="equipo"; t.jugadores_por_equipo=5; t.save()
        Torneo.objects.create(nombre="PC simultáneo",slug="pc",juego="Game",modalidad="equipo",jugadores_por_equipo=5,cupo_equipos=2,bloque="bloque-1",equipamiento="pc",hora_inicio=time(11),hora_fin=time(12),cierre_inscripciones=timezone.now()+timedelta(days=1))
        Torneo.objects.create(nombre="Consolas",slug="consola",juego="Game",modalidad="individual",jugadores_por_equipo=1,cupo_equipos=32,bloque="bloque-1",equipamiento="consola",hora_inicio=time(11),hora_fin=time(12),cierre_inscripciones=timezone.now()+timedelta(days=1))
        response=self._admin().patch("/api/admin/torneos/test/",{"cupo_equipos":4},format="json")
        self.assertEqual(response.status_code,200); self.assertIn("30 estaciones",response.data["advertencia"])

    def test_cargar_torneos_dos_veces_deja_cuatro_sin_duplicar(self):
        call_command("cargar_torneos")
        call_command("cargar_torneos")

        self.assertEqual(Torneo.objects.count(),4)
        self.assertSetEqual(
            set(Torneo.objects.values_list("slug",flat=True)),
            {"mario-kart","valorant","smash","lol-aram"},
        )

    def test_cargar_torneos_configura_los_horarios_ampliados(self):
        call_command("cargar_torneos")

        horarios={
            "mario-kart":(time(11),time(12,30)),
            "valorant":(time(11),time(12,30)),
            "smash":(time(13),time(14,45)),
            "lol-aram":(time(13),time(14,45)),
        }
        for slug,horario in horarios.items():
            torneo=Torneo.objects.get(slug=slug)
            self.assertEqual((torneo.hora_inicio,torneo.hora_fin),horario)

    def test_cargar_torneos_conserva_cupo_ampliado_desde_el_panel(self):
        call_command("cargar_torneos")
        torneo=Torneo.objects.get(slug="smash")
        torneo.cupo_equipos=28
        torneo.save(update_fields=["cupo_equipos"])

        call_command("cargar_torneos")

        torneo.refresh_from_db()
        self.assertEqual(torneo.cupo_equipos,28)

    def test_bloques_cargados_controlan_conflictos_de_inscripcion(self):
        call_command("cargar_torneos")
        mario=Torneo.objects.get(slug="mario-kart")
        smash=Torneo.objects.get(slug="smash")
        participante=attendee(_rut_valido(0),"Ada")
        equipo=Equipo.objects.create(torneo=mario,nombre="Kart Ada",capitan=participante,estado="confirmado")
        Integrante.objects.create(equipo=equipo,asistente=participante)

        with patch("torneos.models.timezone.now",return_value=timezone.make_aware(datetime(2026,9,15))):
            response=APIClient().post(
                "/api/torneos/valorant/inscripcion/",
                {"nombre_equipo":"Valorant Ada","integrantes":[{"rut":participante.rut}]+[{"rut":attendee(_rut_valido(i),f"Jugador {i}").rut} for i in range(1,5)]},
                format="json",
            )
            self.assertEqual(response.status_code,400)
            self.assertIn("Mario Kart 8 Deluxe",str(response.data))

            response=APIClient().post(
                "/api/torneos/smash/inscripcion/",
                {"nombre_equipo":"Smash Ada","integrantes":[{"rut":participante.rut}]},
                format="json",
            )
            self.assertEqual(response.status_code,201)

            response=APIClient().post(
                "/api/torneos/lol-aram/inscripcion/",
                {"nombre_equipo":"League Ada","integrantes":[{"rut":participante.rut}]+[{"rut":attendee(_rut_valido(i),f"Jugador {i}").rut} for i in range(5,9)]},
                format="json",
            )
            self.assertEqual(response.status_code,400)
            self.assertIn("Super Smash Bros. Ultimate",str(response.data))

    def test_cargar_torneos_conserva_estado_y_llave_publicada(self):
        for estado in ("cerrado","sorteado"):
            with self.subTest(estado=estado):
                call_command("cargar_torneos")
                torneo=Torneo.objects.get(slug="valorant")
                torneo.estado=estado
                torneo.llave_publicada=True
                torneo.save(update_fields=["estado","llave_publicada"])

                call_command("cargar_torneos")

                torneo.refresh_from_db()
                self.assertEqual(torneo.estado,estado)
                self.assertTrue(torneo.llave_publicada)
    def test_bracket_tres_equipos_propaga_bye(self):
        t=tournament(); teams=[team(t,"A","12345678-5"),team(t,"B","11111111-1"),team(t,"C","22222222-2")]
        t.estado="cerrado"; t.save(update_fields=["estado"])
        with patch("torneos.services.random.shuffle",lambda x:None): generar_bracket(t)
        self.assertEqual(t.partidas.count(),3)
        bye=t.partidas.get(ronda=1,orden=0); final=t.partidas.get(ronda=2)
        self.assertEqual(bye.estado,"finalizada"); self.assertEqual(bye.ganador,teams[0]); self.assertEqual(final.equipo_a,teams[0])
    def test_corregir_resultado_limpia_rondas_siguientes(self):
        t=tournament()
        for name,rut in [("A","12345678-5"),("B","11111111-1"),("C","22222222-2"),("D","33333333-3")]: team(t,name,rut)
        t.estado="cerrado"; t.save(update_fields=["estado"])
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
    t.estado="cerrado"; t.save(update_fields=["estado"])
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
    assert set(response.data)=={"torneo","slug","estado","modalidad","jugadores_por_equipo","horario","equipos_confirmados","equipos_espera","rondas"}
    assert response.data["modalidad"]=="individual"
    assert response.data["jugadores_por_equipo"]==1

@pytest.mark.django_db
def test_acreditar_y_sortear_solo_equipos_acreditados():
    t=tournament(); teams=[team(t,chr(65+i),_rut_valido(i)) for i in range(3)]
    user=get_user_model().objects.create_user("admin"); client=APIClient(); client.force_authenticate(user)
    for equipo in teams[:2]:
        response=client.patch(f"/api/admin/equipos/{equipo.pk}/",{"acreditado":True},format="json")
        assert response.status_code==200
        equipo.refresh_from_db(); assert equipo.acreditado is True; assert equipo.acreditado_en is not None
    client.post("/api/admin/torneos/test/cerrar-inscripciones/")
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
    client.post("/api/admin/torneos/test/cerrar-inscripciones/")
    response=client.post("/api/admin/torneos/test/sorteo/",{"solo_acreditados":True},format="json")
    assert response.status_code==400
    assert "1 equipos acreditados de 2 inscritos" in response.data["detail"]

@pytest.mark.django_db
def test_walkover_finaliza_y_propaga_ganador():
    t=tournament()
    for i in range(4): team(t,chr(65+i),_rut_valido(i))
    t.estado="cerrado"; t.save(update_fields=["estado"])
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
    t=tournament(); team(t,"A",_rut_valido(0)); team(t,"B",_rut_valido(1)); t.estado="cerrado"; t.save(); generar_bracket(t)
    partida=t.partidas.get(); user=get_user_model().objects.create_user("admin")
    client=APIClient(); client.force_authenticate(user)
    response=client.patch(f"/api/admin/partidas/{partida.pk}/resultado/",{"walkover":"a","score_a":1,"score_b":0},format="json")
    assert response.status_code==400
    assert set(response.data)=={"detail"}
    assert isinstance(response.data["detail"],str)
    partida.refresh_from_db(); assert partida.estado=="pendiente"

@pytest.mark.django_db
def test_errores_de_resultado_tienen_detail_y_no_una_lista_suelta():
    t=tournament(); teams=[team(t,chr(65+i),_rut_valido(i)) for i in range(4)]
    t.estado="cerrado"; t.save(update_fields=["estado"])
    with patch("torneos.services.random.shuffle",lambda x:None): generar_bracket(t)
    partida=t.partidas.get(ronda=1,orden=0)
    incompleta=Partida.objects.create(torneo=t,ronda=9,orden=0,equipo_a=teams[0])
    user=get_user_model().objects.create_user("admin"); client=APIClient(); client.force_authenticate(user)

    casos=[
        (partida,{"score_a":1,"score_b":1},"empate"),
        (incompleta,{"score_a":1,"score_b":0},"ambos equipos"),
        (partida,{"walkover":"a","score_a":1,"score_b":0},"formas excluyentes"),
        (partida,{"walkover":"otro"},"walkover debe ser"),
        (partida,{"score_a":"no-es-entero","score_b":0},"deben ser enteros"),
        (partida,{"score_a":1},"deben ser enteros"),
    ]
    for objetivo,payload,mensaje in casos:
        response=client.patch(f"/api/admin/partidas/{objetivo.pk}/resultado/",payload,format="json")
        assert response.status_code==400
        assert set(response.data)=={"detail"}
        assert isinstance(response.data["detail"],str)
        assert mensaje in response.data["detail"]

@pytest.mark.django_db
def test_corregir_final_requiere_reabrir_y_conserva_llave_publicada():
    t=tournament(); team(t,"A",_rut_valido(0)); team(t,"B",_rut_valido(1))
    t.estado="cerrado"; t.save(update_fields=["estado"])
    with patch("torneos.services.random.shuffle",lambda x:None): generar_bracket(t)
    final=t.partidas.get(); ganador_nuevo=final.equipo_b
    registrar_resultado(final,1,0)
    user=get_user_model().objects.create_user("admin"); client=APIClient(); client.force_authenticate(user)

    response=client.patch(f"/api/admin/partidas/{final.pk}/resultado/",{"score_a":0,"score_b":1},format="json")
    assert response.status_code==400
    assert set(response.data)=={"detail"}
    assert "reabrirlo explícitamente" in response.data["detail"]

    response=client.patch(f"/api/admin/partidas/{final.pk}/resultado/",{"score_a":0,"score_b":1,"reabrir":True},format="json")
    assert response.status_code==200
    final.refresh_from_db(); t.refresh_from_db()
    assert final.ganador==ganador_nuevo
    assert t.estado=="finalizado"
    assert t.llave_publicada is True

@pytest.mark.django_db
def test_corregir_ronda_anterior_reabre_hasta_registrar_la_final():
    t=tournament(); [team(t,chr(65+i),_rut_valido(i)) for i in range(4)]
    t.estado="cerrado"; t.save(update_fields=["estado"])
    with patch("torneos.services.random.shuffle",lambda x:None): generar_bracket(t)
    semifinales=list(t.partidas.filter(ronda=1))
    for semifinal in semifinales: registrar_resultado(semifinal,1,0)
    final=t.partidas.get(ronda=2); registrar_resultado(final,1,0)
    user=get_user_model().objects.create_user("admin"); client=APIClient(); client.force_authenticate(user)

    response=client.patch(f"/api/admin/partidas/{semifinales[0].pk}/resultado/",{"score_a":0,"score_b":1,"reabrir":True},format="json")
    assert response.status_code==200
    t.refresh_from_db(); final.refresh_from_db()
    assert t.estado=="en_curso"
    assert t.llave_publicada is True
    assert final.estado=="pendiente"

    response=client.patch(f"/api/admin/partidas/{final.pk}/resultado/",{"score_a":1,"score_b":0},format="json")
    assert response.status_code==200
    t.refresh_from_db()
    assert t.estado=="finalizado"
    assert t.llave_publicada is True

@pytest.mark.django_db
def test_bracket_no_publicado_oculta_equipos_y_rondas():
    t=tournament(); team(t,"Los Pro",_rut_valido(0))
    response=APIClient().get("/api/torneos/test/bracket/")
    assert response.status_code==200
    assert response.data["rondas"]==[]
    assert response.data["modalidad"]==t.modalidad
    assert response.data["jugadores_por_equipo"]==t.jugadores_por_equipo
    assert "equipos_confirmados" not in response.data
    assert "equipos_espera" not in response.data

@pytest.mark.django_db
def test_cambios_durante_inscripcion_no_consumen_comodines_del_capitan():
    t=tournament(); t.modalidad="equipo"; t.jugadores_por_equipo=2; t.save(update_fields=["modalidad","jugadores_por_equipo"])
    equipo=team(t,"A",_rut_valido(0)); integrante=attendee(_rut_valido(1),"Integrante")
    Integrante.objects.create(equipo=equipo,asistente=integrante)
    client=APIClient(); actual=integrante

    for numero in (2,3):
        entrante=attendee(_rut_valido(numero),f"Cambio {numero}")
        response=client.post(f"/api/equipos/{equipo.pk}/integrantes/",{
            "codigo_capitan":equipo.capitan.codigo,"rut_saliente":actual.rut,
            "rut_entrante":entrante.rut,"gamertag":f"cambio-{numero}"},format="json")
        assert response.status_code==200
        actual=entrante

    t.estado="cerrado"; t.save(update_fields=["estado"])
    assert PaseSerializer(equipo.capitan).data["torneos"][0]["comodines_restantes"]==2

    for restante,numero in ((1,4),(0,5)):
        entrante=attendee(_rut_valido(numero),f"Comodín {numero}")
        response=client.post(f"/api/equipos/{equipo.pk}/integrantes/",{
            "codigo_capitan":equipo.capitan.codigo,"rut_saliente":actual.rut,
            "rut_entrante":entrante.rut,"codigo_entrante":entrante.codigo,
            "gamertag":f"comodin-{numero}"},format="json")
        assert response.status_code==200
        assert response.data["comodines_restantes"]==restante
        actual=entrante

    assert equipo.cambios.filter(origen="capitan",tras_cierre=False).count()==2
    assert equipo.cambios.filter(origen="capitan",tras_cierre=True).count()==2

@pytest.mark.django_db
def test_capitan_no_puede_reemplazar_por_integrante_de_otro_equipo():
    t=tournament(); t.modalidad="equipo"; t.jugadores_por_equipo=2; t.save(update_fields=["modalidad","jugadores_por_equipo"])
    primero=team(t,"A",_rut_valido(0)); segundo=team(t,"B",_rut_valido(1))
    response=APIClient().post(f"/api/equipos/{primero.pk}/integrantes/",{
        "codigo_capitan":primero.capitan.codigo,"rut_saliente":primero.capitan.rut,
        "rut_entrante":segundo.capitan.rut,"gamertag":"nuevo"},format="json")
    # La validación del capitán saliente tiene precedencia; agregamos un segundo integrante reemplazable.
    assert response.status_code==400
    suplente=attendee(_rut_valido(2),"Suplente"); Integrante.objects.create(equipo=primero,asistente=suplente)
    response=APIClient().post(f"/api/equipos/{primero.pk}/integrantes/",{
        "codigo_capitan":primero.capitan.codigo,"rut_saliente":suplente.rut,
        "rut_entrante":segundo.capitan.rut,"gamertag":"nuevo"},format="json")
    assert response.status_code==400
    assert "ya participa" in response.data["detail"]

@pytest.mark.django_db
def test_admin_reemplaza_con_llave_en_curso_sin_modificar_partidas_y_audita():
    t=tournament(); reemplazado=team(t,"A",_rut_valido(0)); team(t,"B",_rut_valido(1))
    t.estado="cerrado"; t.save(update_fields=["estado"]); generar_bracket(t)
    t.estado="en_curso"; t.save(update_fields=["estado"])
    referencias=list(t.partidas.values_list("equipo_a_id","equipo_b_id")); saliente=reemplazado.capitan
    entrante=attendee(_rut_valido(2),"Comodín"); user=get_user_model().objects.create_user("coordinador")
    client=APIClient(); client.force_authenticate(user)
    response=client.post(f"/api/admin/equipos/{reemplazado.pk}/reemplazar/",{
        "rut_saliente":saliente.rut,"rut_entrante":entrante.rut,"motivo":"no_se_presento","gamertag":"wild"},format="json")
    assert response.status_code==200
    reemplazado.refresh_from_db(); cambio=CambioIntegrante.objects.get(equipo=reemplazado)
    assert reemplazado.capitan==entrante and cambio.realizado_por==user
    assert response.data["integrantes"][0]["es_capitan"] is True
    assert response.data["integrantes"][0]["es_comodin"] is True
    assert list(t.partidas.values_list("equipo_a_id","equipo_b_id"))==referencias
    assert PaseSerializer(entrante).data["torneos"][0]["slug"]==t.slug
    assert PaseSerializer(saliente).data["torneos"]==[]

@pytest.mark.django_db
def test_admin_reemplazo_valida_finalizado_registro_equipo_nombre_y_forzar():
    t=tournament(); t.bloque="uno"; t.save(update_fields=["bloque"]); objetivo=team(t,"A",_rut_valido(0))
    otro=team(t,"Nombre ocupado",_rut_valido(1)); no_registrado=_rut_valido(9)
    user=get_user_model().objects.create_user("coordinador"); client=APIClient(); client.force_authenticate(user)
    url=f"/api/admin/equipos/{objetivo.pk}/reemplazar/"
    base={"rut_saliente":objetivo.capitan.rut,"motivo":"otro"}
    response=client.post(url,base|{"rut_entrante":no_registrado},format="json")
    assert response.status_code==400 and "no está registrado" in response.data["detail"]
    response=client.post(url,base|{"rut_entrante":otro.capitan.rut},format="json")
    assert response.status_code==400 and "ya participa" in response.data["detail"]
    bloque=Torneo.objects.create(nombre="Otro torneo",slug="otro",juego="Game",modalidad="individual",jugadores_por_equipo=1,cupo_equipos=4,bloque="uno",hora_inicio=time(11),hora_fin=time(12),cierre_inscripciones=timezone.now()+timedelta(days=1))
    comodin=attendee(_rut_valido(2),"Comodín"); e=Equipo.objects.create(torneo=bloque,nombre="Otro",capitan=comodin,estado="confirmado"); Integrante.objects.create(equipo=e,asistente=comodin)
    response=client.post(url,base|{"rut_entrante":comodin.rut},format="json")
    assert response.status_code==400 and "Otro torneo" in response.data["detail"]
    response=client.post(url,base|{"rut_entrante":comodin.rut,"forzar":True,"nombre_equipo":"nombre OCUPADO"},format="json")
    assert response.status_code==400 and "nombre ya está tomado" in response.data["detail"]
    response=client.post(url,base|{"rut_entrante":comodin.rut,"forzar":True},format="json")
    assert response.status_code==200
    t.estado="finalizado"; t.save(update_fields=["estado"]); nuevo=attendee(_rut_valido(3),"Nuevo")
    response=client.post(url,{"rut_saliente":comodin.rut,"rut_entrante":nuevo.rut,"motivo":"otro"},format="json")
    assert response.status_code==400 and "ya finalizó" in response.data["detail"]

@pytest.mark.django_db
def test_admin_capitan_candidatos_y_autenticacion():
    t=tournament(); t.bloque="uno"; t.save(update_fields=["bloque"]); equipo=team(t,"A",_rut_valido(0))
    fuera=attendee(_rut_valido(1),"Fuera"); client=APIClient()
    assert client.patch(f"/api/admin/equipos/{equipo.pk}/",{"capitan_rut":fuera.rut},format="json").status_code==401
    assert client.post(f"/api/admin/equipos/{equipo.pk}/reemplazar/",{},format="json").status_code==401
    assert client.get("/api/admin/torneos/test/candidatos/?q=Fu").status_code==401
    client.force_authenticate(get_user_model().objects.create_user("coordinador"))
    response=client.patch(f"/api/admin/equipos/{equipo.pk}/",{"capitan_rut":fuera.rut},format="json")
    assert response.status_code==400 and "integrante" in response.data["detail"]
    assert client.get("/api/admin/torneos/test/candidatos/?q=F").data==[]
    otro=Torneo.objects.create(nombre="Conflicto",slug="conflicto",juego="Game",modalidad="individual",jugadores_por_equipo=1,cupo_equipos=4,bloque="uno",hora_inicio=time(11),hora_fin=time(12),cierre_inscripciones=timezone.now()+timedelta(days=1))
    e=Equipo.objects.create(torneo=otro,nombre="Fuera",capitan=fuera,estado="confirmado"); Integrante.objects.create(equipo=e,asistente=fuera)
    response=client.get("/api/admin/torneos/test/candidatos/?q=Fu")
    assert response.status_code==200 and response.data[0]["rut"]==fuera.rut
    assert response.data[0]["conflicto_bloque"]=="Conflicto"
    response=client.get(f"/api/admin/torneos/test/candidatos/?q={equipo.capitan.rut[:2]}")
    assert all(x["rut"]!=equipo.capitan.rut for x in response.data)

@pytest.mark.django_db
def test_retirar_equipo_promueve_primero_en_espera():
    t=tournament(1); confirmado=team(t,"A",_rut_valido(0))
    espera_uno=team(t,"B",_rut_valido(1)); espera_uno.estado="espera"; espera_uno.save()
    espera_dos=team(t,"C",_rut_valido(2)); espera_dos.estado="espera"; espera_dos.save()
    response=APIClient().delete(f"/api/equipos/{confirmado.pk}/",{"codigo_capitan":confirmado.capitan.codigo},format="json")
    assert response.status_code==200
    confirmado.refresh_from_db(); espera_uno.refresh_from_db(); espera_dos.refresh_from_db()
    assert confirmado.estado=="retirado"; assert espera_uno.estado=="confirmado"; assert espera_dos.estado=="espera"
    assert t.promociones.filter(equipo=espera_uno).exists()

@pytest.mark.django_db
def test_equipo_retirado_no_puede_gestionarse_desde_el_pase():
    t=tournament(); equipo=team(t,"A",_rut_valido(0)); client=APIClient()
    response=client.delete(f"/api/equipos/{equipo.pk}/",{"codigo_capitan":equipo.capitan.codigo},format="json")
    assert response.status_code==200

    equipo.refresh_from_db()
    torneo_en_pase=PaseSerializer(equipo.capitan).data["torneos"][0]
    assert torneo_en_pase["puede_gestionar"] is False

    response=client.patch(f"/api/equipos/{equipo.pk}/",{
        "codigo_capitan":equipo.capitan.codigo,"nombre_equipo":"Renombrado"},format="json")
    assert response.status_code==400
    assert response.data["detail"]=="El equipo está retirado."
