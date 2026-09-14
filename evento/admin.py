from django.contrib import admin
from .models import Asistente, RetiroCompleto
@admin.register(Asistente)
class AsistenteAdmin(admin.ModelAdmin):
    list_display=["nombre","apellido","rut","codigo","tipo","aporte","completos_retirados"]; search_fields=["nombre","apellido","rut","codigo"]; list_filter=["tipo","area","aporte"]
@admin.register(RetiroCompleto)
class RetiroAdmin(admin.ModelAdmin):
    list_display=["asistente","cantidad","validado_por","creado_en"]; search_fields=["asistente__rut","asistente__codigo"]; list_filter=["cantidad","creado_en"]
