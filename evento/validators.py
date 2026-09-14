import re
from django.core.exceptions import ValidationError

def normalizar_rut(value):
    cleaned = re.sub(r"[^0-9kK]", "", str(value)).upper()
    if len(cleaned) < 2:
        raise ValidationError("RUT inválido.")
    return f"{cleaned[:-1]}-{cleaned[-1]}"

def validar_rut(value):
    rut = normalizar_rut(value)
    body, supplied = rut.split("-")
    if not body.isdigit():
        raise ValidationError("RUT inválido.")
    total, factor = 0, 2
    for digit in reversed(body):
        total += int(digit) * factor
        factor = 2 if factor == 7 else factor + 1
    result = 11 - total % 11
    expected = "0" if result == 11 else "K" if result == 10 else str(result)
    if supplied != expected:
        raise ValidationError("Dígito verificador del RUT inválido.")
    return rut

def enmascarar_rut(value):
    body, dv = normalizar_rut(value).split("-")
    visible = body[:2]
    masked = visible + "." + "".join("X" if i else d for i, d in enumerate(body[2:]))
    return f"{masked}-{dv}"
