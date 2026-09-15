from django.contrib import admin
from .models import AlumnoHabilitado, Area, Asistente, Carrera, ConfiguracionEvento, RetiroCompleto

@admin.register(ConfiguracionEvento)
class ConfiguracionEventoAdmin(admin.ModelAdmin):
    def has_add_permission(self,request):
        return not ConfiguracionEvento.objects.exists()
    def has_delete_permission(self,request,obj=None): return False
@admin.register(Area)
class AreaAdmin(admin.ModelAdmin):
    list_display=["nombre","slug","orden","activa"]
    search_fields=["nombre","slug"]
    list_filter=["activa"]
@admin.register(Carrera)
class CarreraAdmin(admin.ModelAdmin):
    list_display=["nombre","area","slug","activa"]
    search_fields=["nombre","slug","area__nombre"]
    list_filter=["area","activa"]
@admin.register(Asistente)
class AsistenteAdmin(admin.ModelAdmin):
    list_display=["nombre","apellido","rut","codigo","tipo","aporte","completos_retirados"]; search_fields=["nombre","apellido","rut","codigo"]; list_filter=["tipo","area","aporte"]
@admin.register(AlumnoHabilitado)
class AlumnoHabilitadoAdmin(admin.ModelAdmin):
    list_display=["nombre","apellido","rut","email","carrera","lote","creado_en"]
    search_fields=["rut","nombre","apellido","email"]
    list_filter=["carrera","lote"]
@admin.register(RetiroCompleto)
class RetiroAdmin(admin.ModelAdmin):
    list_display=["asistente","cantidad","validado_por","creado_en"]; search_fields=["asistente__rut","asistente__codigo"]; list_filter=["cantidad","creado_en"]
