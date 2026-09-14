from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
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
        with self.assertRaises(ValidationError): registrar_retiro(a,1,user)
