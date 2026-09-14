from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework.test import APIClient
from .models import Asistente
from .services import registrar_retiro
from .validators import normalizar_rut, validar_rut

def attendee(rut="12345678-5",name="Ada"):
    return Asistente.objects.create(nombre=name,apellido="Lovelace",rut=rut,email="ada@example.com",tipo="externo",area="informatica")

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

    def test_retiro_errores_tienen_detail_y_acepta_cantidad_string(self):
        a=attendee(); user=get_user_model().objects.create_user("operator"); client=APIClient(); client.force_authenticate(user)
        ok=client.post("/api/admin/retiros/",{"codigo":a.codigo,"cantidad":"1"},format="json")
        self.assertEqual(ok.status_code,201)
        too_many=client.post("/api/admin/retiros/",{"codigo":a.codigo,"cantidad":2},format="json")
        self.assertEqual(too_many.status_code,400); self.assertEqual(too_many.data,{"detail":"Solo le queda 1 completo disponible."})
        invalid=client.post("/api/admin/retiros/",{"codigo":a.codigo,"cantidad":"dos"},format="json")
        self.assertEqual(invalid.status_code,400); self.assertEqual(invalid.data,{"detail":"La cantidad debe ser 1 o 2."})
