from rest_framework import serializers
from .models import Asistente, RetiroCompleto
from .validators import enmascarar_rut, validar_rut

class AsistenteSerializer(serializers.ModelSerializer):
    completos_disponibles=serializers.IntegerField(read_only=True)
    class Meta:
        model=Asistente
        fields=["nombre","apellido","rut","email","telefono","tipo","area","carrera","aporte","codigo","completos_asignados","completos_retirados","completos_disponibles","creado_en"]
        read_only_fields=["codigo","completos_asignados","completos_retirados","creado_en"]
    def validate_rut(self,value): return validar_rut(value)

class PaseSerializer(serializers.ModelSerializer):
    rut=serializers.SerializerMethodField(); completos_disponibles=serializers.IntegerField(read_only=True)
    torneos=serializers.SerializerMethodField()
    class Meta:
        model=Asistente
        fields=["nombre","apellido","rut","codigo","completos_asignados","completos_retirados","completos_disponibles","torneos"]
    def get_rut(self,obj): return enmascarar_rut(obj.rut)
    def get_torneos(self,obj):
        return [{"slug":x.equipo.torneo.slug,"nombre":x.equipo.torneo.nombre,"equipo":x.equipo.nombre} for x in obj.participaciones.select_related("equipo__torneo")]

class RetiroSerializer(serializers.ModelSerializer):
    asistente=serializers.SerializerMethodField(); validado_por=serializers.StringRelatedField()
    class Meta: model=RetiroCompleto; fields=["id","asistente","cantidad","validado_por","creado_en"]
    def get_asistente(self,obj):
        return {"nombre":obj.asistente.nombre,"apellido":obj.asistente.apellido,"codigo":obj.asistente.codigo}
