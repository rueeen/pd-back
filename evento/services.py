from django.core.exceptions import ValidationError
from django.db import transaction
from .models import Asistente, RetiroCompleto

@transaction.atomic
def registrar_retiro(asistente,cantidad,usuario):
    if not isinstance(cantidad,int) or not 1 <= cantidad <= 2:
        raise ValidationError("La cantidad debe ser 1 o 2.")
    locked=Asistente.objects.select_for_update().get(pk=asistente.pk)
    if cantidad > locked.completos_disponibles:
        raise ValidationError(f"Solo le quedan {locked.completos_disponibles} completos disponibles.")
    locked.completos_retirados += cantidad
    locked.save(update_fields=["completos_retirados"])
    return RetiroCompleto.objects.create(asistente=locked,cantidad=cantidad,validado_por=usuario)
