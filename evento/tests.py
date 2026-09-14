from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient
from .models import Area, Asistente, Carrera
from .services import registrar_retiro
from .validators import normalizar_rut, validar_rut

def attendee(rut="12345678-5",name="Ada"):
    return Asistente.objects.create(nombre=name,apellido="Lovelace",rut=rut,email="ada@example.com",tipo="externo")

class EventoTests(TestCase):
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

    def test_cargar_carreras_es_idempotente(self):
        Carrera.objects.all().delete(); Area.objects.all().delete()
        call_command("cargar_carreras"); call_command("cargar_carreras")
        self.assertEqual(Area.objects.count(),10)
        self.assertEqual(Carrera.objects.count(),18)
