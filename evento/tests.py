from unittest.mock import patch
import importlib.util
import io
from unittest import skipUnless
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command, CommandError
from django.test import TestCase
from rest_framework.test import APIClient
from .models import AlumnoHabilitado, Area, Asistente, Carrera, ConfiguracionEvento
from .services import registrar_retiro
from .validators import normalizar_rut, validar_rut

def attendee(rut="12345678-5",name="Ada"):
    return Asistente.objects.create(nombre=name,apellido="Lovelace",rut=rut,email="ada@example.com",tipo="externo")

class EventoTests(TestCase):
    def test_cupo_rechaza_nuevo_pero_permite_recuperar_existente(self):
        existing=attendee(); config=ConfiguracionEvento.obtener(); config.cupo_asistentes=1; config.save()
        client=APIClient()
        rejected=client.post("/api/asistentes/",{"nombre":"Grace","apellido":"Hopper","rut":"11111111-1","email":"grace@example.com","tipo":"externo"},format="json")
        recovered=client.post("/api/asistentes/",{"rut":existing.rut,"email":existing.email},format="json")
        self.assertEqual(rejected.status_code,409)
        self.assertEqual(recovered.status_code,200)
        self.assertTrue(recovered.data["recuperado"])

    def test_aplicar_completos_respeta_retiros_superiores(self):
        protegido=attendee(); protegido.completos_asignados=3; protegido.completos_retirados=2; protegido.save()
        actualizable=attendee("11111111-1","Grace")
        user=get_user_model().objects.create_user("admin-config"); client=APIClient(); client.force_authenticate(user)
        response=client.patch("/api/admin/configuracion/",{"completos_por_asistente":1,"aplicar_a_existentes":True},format="json")
        protegido.refresh_from_db(); actualizable.refresh_from_db()
        self.assertEqual(response.status_code,200); self.assertEqual(response.data["sin_actualizar"],1)
        self.assertEqual(protegido.completos_asignados,3); self.assertEqual(actualizable.completos_asignados,1)

    def test_codigo_aleatorio_y_unico(self):
        a=attendee(); b=attendee("11111111-1","Grace")
        self.assertEqual(len(a.codigo),10); self.assertNotEqual(a.codigo,b.codigo)
        self.assertNotIn("I",a.codigo); self.assertNotIn("O",a.codigo)
    def test_rut_se_normaliza_y_valida(self):
        self.assertEqual(normalizar_rut("12.345.678-5"),"12345678-5")
        self.assertEqual(validar_rut("12.345.678-5"),"12345678-5")
        with self.assertRaises(ValidationError): validar_rut("12.345.678-9")
    def test_no_permite_canjear_mas_de_dos(self):
        a=attendee(); user=get_user_model().objects.create_user("operator")
        registrar_retiro(a,2,user)
        with self.assertRaisesMessage(ValidationError,"Ya retiró sus 2 completos."): registrar_retiro(a,1,user)

    def test_recuperacion_exige_mismo_email_y_no_filtra_datos(self):
        a=attendee(); client=APIClient()
        denied=client.post("/api/asistentes/",{"rut":a.rut,"email":"intruso@example.com"},format="json")
        self.assertEqual(denied.status_code,409); self.assertEqual(set(denied.data),{"detail"})
        recovered=client.post("/api/asistentes/",{"rut":a.rut,"email":"ADA@EXAMPLE.COM"},format="json")
        self.assertEqual(recovered.status_code,200); self.assertTrue(recovered.data["recuperado"])

    def test_endpoint_recuperar_pase_no_revela_si_el_rut_existe(self):
        a=attendee(); client=APIClient()
        correcto=client.post("/api/pase/recuperar/",{"rut":a.rut,"email":"ADA@EXAMPLE.COM"},format="json")
        correo_incorrecto=client.post("/api/pase/recuperar/",{"rut":a.rut,"email":"otro@example.com"},format="json")
        rut_inexistente=client.post("/api/pase/recuperar/",{"rut":"22222222-2","email":"otro@example.com"},format="json")
        self.assertEqual(correcto.status_code,200); self.assertEqual(correcto.data,{"codigo":a.codigo})
        self.assertEqual(correo_incorrecto.status_code,404); self.assertEqual(rut_inexistente.status_code,404)
        self.assertEqual(correo_incorrecto.data,rut_inexistente.data)

    def test_retiro_errores_tienen_detail_y_acepta_cantidad_string(self):
        a=attendee(); user=get_user_model().objects.create_user("operator"); client=APIClient(); client.force_authenticate(user)
        ok=client.post("/api/admin/retiros/",{"codigo":a.codigo,"cantidad":"1"},format="json")
        self.assertEqual(ok.status_code,201)
        too_many=client.post("/api/admin/retiros/",{"codigo":a.codigo,"cantidad":2},format="json")
        self.assertEqual(too_many.status_code,400); self.assertEqual(too_many.data,{"detail":"Solo le queda 1 completo disponible."})
        invalid=client.post("/api/admin/retiros/",{"codigo":a.codigo,"cantidad":"dos"},format="json")
        self.assertEqual(invalid.status_code,400); self.assertEqual(invalid.data,{"detail":"La cantidad debe ser 1 o 2."})

class CatalogoTests(TestCase):
    def setUp(self):
        self.area=Area.objects.create(nombre="Área uno",slug="area-uno",orden=1)
        self.otra=Area.objects.create(nombre="Área dos",slug="area-dos",orden=2)
        self.carrera=Carrera.objects.create(area=self.area,nombre="Carrera uno",slug="carrera-uno")
        self.otra_carrera=Carrera.objects.create(area=self.otra,nombre="Carrera dos",slug="carrera-dos")
        self.base={"nombre":"Ana","apellido":"Díaz","rut":"12345678-5","email":"ana@example.com","aporte":"ninguno"}

    def test_carrera_de_otra_area_es_rechazada(self):
        response=APIClient().post("/api/asistentes/",self.base|{"tipo":"estudiante","area":"area-uno","carrera":"carrera-dos"},format="json")
        self.assertEqual(response.status_code,400)
        self.assertEqual(response.data["carrera"][0],"Esta carrera no corresponde al área seleccionada.")

    def test_estudiante_sin_area_es_rechazado(self):
        response=APIClient().post("/api/asistentes/",self.base|{"tipo":"estudiante","carrera":"carrera-uno"},format="json")
        self.assertEqual(response.status_code,400)
        self.assertIn("area",response.data)

    def test_docente_sin_area_es_aceptado(self):
        response=APIClient().post("/api/asistentes/",self.base|{"tipo":"docente"},format="json")
        self.assertEqual(response.status_code,201)
        self.assertIsNone(response.data["area"])
        self.assertIsNone(response.data["carrera"])

    def test_catalogo_solo_incluye_elementos_activos(self):
        self.otra.activa=False; self.otra.save()
        self.carrera.activa=False; self.carrera.save()
        response=APIClient().get("/api/catalogo/areas/")
        self.assertEqual(response.status_code,200)
        catalogo={item["slug"]:item for item in response.data}
        self.assertNotIn("area-dos",catalogo)
        self.assertEqual(catalogo["area-uno"]["carreras"],[])

    def test_configuracion_publica_incluye_areas_prioritarias_ordenadas(self):
        config=ConfiguracionEvento.obtener()
        self.assertEqual(APIClient().get("/api/configuracion/").data["areas_prioritarias"],[])

        config.areas_prioritarias.add(self.otra,self.area)
        response=APIClient().get("/api/configuracion/")

        self.assertEqual(response.status_code,200)
        self.assertEqual(response.data["areas_prioritarias"],[
            {"slug":"area-uno","nombre":"Área uno"},
            {"slug":"area-dos","nombre":"Área dos"},
        ])
        self.assertNotIn("restriccion_todos_los_tipos",response.data)

    def test_restriccion_todos_los_tipos_solo_se_expone_y_edita_en_admin(self):
        user=get_user_model().objects.create_user("admin-restriccion"); client=APIClient(); client.force_authenticate(user)
        response=client.patch("/api/admin/configuracion/",{"restriccion_todos_los_tipos":True},format="json")
        self.assertEqual(response.status_code,200)
        self.assertTrue(response.data["restriccion_todos_los_tipos"])
        self.assertTrue(client.get("/api/admin/configuracion/").data["restriccion_todos_los_tipos"])
        self.assertNotIn("restriccion_todos_los_tipos",APIClient().get("/api/configuracion/").data)

    def test_cargar_carreras_es_idempotente(self):
        Carrera.objects.all().delete(); Area.objects.all().delete()
        call_command("cargar_carreras"); call_command("cargar_carreras")
        self.assertEqual(Area.objects.count(),10)
        self.assertEqual(Carrera.objects.count(),18)

    def test_pase_incluye_carrera_y_area_pero_no_datos_de_contacto(self):
        asistente=attendee()
        asistente.area=self.area; asistente.carrera=self.carrera; asistente.save()
        data=APIClient().get(f"/api/pase/{asistente.codigo}/").data
        self.assertEqual(data["area_nombre"],self.area.nombre)
        self.assertEqual(data["carrera_nombre"],self.carrera.nombre)
        self.assertNotIn("email",data); self.assertNotIn("telefono",data)

    def test_throttle_permite_mas_de_veinte_registros_desde_una_ip(self):
        client=APIClient()
        for indice in range(21):
            response=client.post("/api/asistentes/",{
                "nombre":"Ensayo","apellido":str(indice),"rut":_rut_valido_registro(indice),
                "email":f"throttle-{indice}@example.test","tipo":"docente","aporte":"ninguno",
            },format="json",REMOTE_ADDR="192.0.2.25")
            self.assertEqual(response.status_code,201,response.data)

class PadronTests(TestCase):
    def setUp(self):
        self.area=Area.objects.create(nombre="Área prioritaria",slug="prioritaria",orden=1)
        self.otra_area=Area.objects.create(nombre="Otra área",slug="otra",orden=2)
        self.carrera=Carrera.objects.create(area=self.area,nombre="Carrera Prioritaria",slug="carrera-prioritaria")
        self.otra_carrera=Carrera.objects.create(area=self.otra_area,nombre="Carrera Secundaria",slug="carrera-secundaria")
        self.config=ConfiguracionEvento.obtener(); self.config.registro_restringido=True; self.config.save()
        self.config.areas_prioritarias.add(self.area)
        self.base={"nombre":"Ana","apellido":"Díaz","email":"ana@example.com","tipo":"estudiante","area":self.area.slug,"carrera":self.carrera.slug}

    def test_rechazos_usan_el_mismo_mensaje(self):
        self.config.restriccion_todos_los_tipos=True; self.config.save()
        fuera=APIClient().post("/api/asistentes/",self.base|{"rut":"12345678-5"},format="json")
        AlumnoHabilitado.objects.create(rut="11111111-1",nombre="Otra",apellido="Persona",carrera=self.otra_carrera)
        otra_area=APIClient().post("/api/asistentes/",self.base|{"rut":"11111111-1"},format="json")
        externo=APIClient().post("/api/asistentes/",self.base|{"rut":"22222222-2","tipo":"externo","area":None,"carrera":None},format="json")
        self.assertEqual(fuera.status_code,403); self.assertEqual(otra_area.status_code,403); self.assertEqual(externo.status_code,403)
        self.assertEqual(fuera.data,otra_area.data); self.assertEqual(fuera.data,externo.data)

    def test_habilitado_sin_carrera_es_aceptado_con_areas_prioritarias(self):
        self.config.restriccion_todos_los_tipos=True; self.config.save()
        AlumnoHabilitado.objects.create(rut="11111111-1",nombre="Luis",apellido="Pérez")
        response=APIClient().post("/api/asistentes/",self.base|{"rut":"11111111-1","tipo":"funcionario","area":None,"carrera":None},format="json")
        self.assertEqual(response.status_code,201)

    def test_docente_del_padron_en_area_no_prioritaria_es_rechazado(self):
        self.config.restriccion_todos_los_tipos=True; self.config.save()
        AlumnoHabilitado.objects.create(rut="11111111-1",nombre="Otra",apellido="Persona",carrera=self.otra_carrera)
        response=APIClient().post("/api/asistentes/",self.base|{"rut":"11111111-1","tipo":"docente","area":None,"carrera":None},format="json")
        self.assertEqual(response.status_code,403)

    def test_con_interruptor_apagado_habilitado_y_externo_son_aceptados(self):
        self.assertFalse(self.config.restriccion_todos_los_tipos)
        AlumnoHabilitado.objects.create(rut="12345678-5",nombre="Ana",apellido="Díaz",carrera=self.carrera)
        estudiante=APIClient().post("/api/asistentes/",self.base|{"rut":"12345678-5"},format="json")
        externo=APIClient().post("/api/asistentes/",{"nombre":"Luis","apellido":"Pérez","rut":"11111111-1","email":"luis@example.com","tipo":"externo"},format="json")
        self.assertEqual(estudiante.status_code,201); self.assertEqual(externo.status_code,201)

    def test_recuperacion_no_se_restringe(self):
        self.config.restriccion_todos_los_tipos=True; self.config.save()
        existente=attendee()
        response=APIClient().post("/api/pase/recuperar/",{"rut":existente.rut,"email":existente.email},format="json")
        self.assertEqual(response.status_code,200); self.assertEqual(response.data["codigo"],existente.codigo)

    def test_prellenado_no_expone_padron_con_restriccion_apagada(self):
        AlumnoHabilitado.objects.create(rut="12345678-5",nombre="Ana",apellido="Díaz",carrera=self.carrera)
        self.config.registro_restringido=False; self.config.save()
        self.assertEqual(APIClient().get("/api/padron/12345678-5/").status_code,404)

    def test_borrado_se_rechaza_con_restriccion_activa(self):
        user=get_user_model().objects.create_user("admin-padron"); client=APIClient(); client.force_authenticate(user)
        response=client.delete("/api/admin/padron/",{"confirmacion":"BORRAR PADRON"},format="json")
        self.assertEqual(response.status_code,400)

    @skipUnless(importlib.util.find_spec("openpyxl"),"openpyxl no está instalado en este entorno")
    def test_reemplazo_invalido_deja_padron_anterior_intacto(self):
        from openpyxl import Workbook
        anterior=AlumnoHabilitado.objects.create(rut="12345678-5",nombre="Anterior",apellido="Persona",carrera=self.carrera)
        wb=Workbook(); ws=wb.active; ws.title="Alumnos"
        ws.append(["RUT","Nombre","Apellido","Correo","Carrera"])
        ws.append(["11.111.111-9","Inválido","Ejemplo","test@example.com",self.carrera.nombre])
        content=io.BytesIO(); wb.save(content); content.seek(0); content.name="padron.xlsx"
        user=get_user_model().objects.create_user("admin-import"); client=APIClient(); client.force_authenticate(user)
        response=client.post("/api/admin/padron/cargar/",{"archivo":content,"modo":"reemplazar"},format="multipart")
        self.assertEqual(response.status_code,400)
        self.assertTrue(AlumnoHabilitado.objects.filter(pk=anterior.pk).exists())


class DatosPruebaTests(TestCase):
    def test_limpiar_se_niega_con_debug_falso(self):
        with self.settings(DEBUG=False):
            with self.assertRaisesMessage(CommandError,"DEBUG=False"):
                call_command("datos_prueba",limpiar=True)


def _rut_valido_registro(numero):
    cuerpo=str(40000000+numero)
    total=sum(int(d)*factor for d,factor in zip(reversed(cuerpo),(2,3,4,5,6,7,2,3)))
    resultado=11-total%11
    dv="0" if resultado==11 else "K" if resultado==10 else str(resultado)
    return f"{cuerpo}-{dv}"
