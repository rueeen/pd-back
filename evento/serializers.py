from rest_framework import serializers
from .models import Area, Asistente, Carrera, ConfiguracionEvento, RetiroCompleto
from .validators import enmascarar_rut, validar_rut
from torneos.services import (autorizacion_gestion_capitan, autorizacion_reemplazo_capitan,
                              comodines_restantes_capitan)

class AsistenteSerializer(serializers.ModelSerializer):
    area=serializers.SlugRelatedField(slug_field="slug",queryset=Area.objects.filter(activa=True),allow_null=True,required=False)
    carrera=serializers.SlugRelatedField(slug_field="slug",queryset=Carrera.objects.filter(activa=True),allow_null=True,required=False)
    area_nombre=serializers.CharField(source="area.nombre",read_only=True,allow_null=True)
    carrera_nombre=serializers.CharField(source="carrera.nombre",read_only=True,allow_null=True)
    completos_disponibles=serializers.IntegerField(read_only=True)
    class Meta:
        model=Asistente
        fields=["nombre","apellido","rut","email","telefono","tipo","area","area_nombre","carrera","carrera_nombre","aporte","codigo","completos_asignados","completos_retirados","completos_disponibles","creado_en"]
        read_only_fields=["codigo","completos_asignados","completos_retirados","creado_en"]
    def validate_rut(self,value): return validar_rut(value)
    def validate(self,attrs):
        tipo=attrs.get("tipo",getattr(self.instance,"tipo",None))
        area=attrs.get("area",getattr(self.instance,"area",None))
        carrera=attrs.get("carrera",getattr(self.instance,"carrera",None))
        errors={}
        if tipo == "estudiante":
            if area is None: errors["area"]="Este campo es obligatorio para estudiantes."
            if carrera is None: errors["carrera"]="Este campo es obligatorio para estudiantes."
        if carrera is not None and (area is None or carrera.area_id != area.id):
            errors["carrera"]="Esta carrera no corresponde al área seleccionada."
        if errors: raise serializers.ValidationError(errors)
        return attrs

class AsistenteAdminListaSerializer(serializers.ModelSerializer):
    area=serializers.SlugRelatedField(slug_field="slug",read_only=True)
    carrera=serializers.SlugRelatedField(slug_field="slug",read_only=True)
    area_nombre=serializers.CharField(source="area.nombre",read_only=True,allow_null=True)
    carrera_nombre=serializers.CharField(source="carrera.nombre",read_only=True,allow_null=True)
    completos_disponibles=serializers.IntegerField(read_only=True)
    en_padron=serializers.SerializerMethodField(); torneos=serializers.SerializerMethodField()
    class Meta:
        model=Asistente
        fields=["codigo","nombre","apellido","rut","email","telefono","tipo","area","area_nombre","carrera","carrera_nombre","aporte","completos_asignados","completos_retirados","completos_disponibles","creado_en","en_padron","torneos"]
        read_only_fields=fields
    def get_en_padron(self,obj): return obj.rut in self.context.get("ruts_padron",set())
    def get_torneos(self,obj):
        return [{"slug":p.equipo.torneo.slug,"nombre":p.equipo.torneo.nombre,"equipo":p.equipo.nombre,"estado_equipo":p.equipo.estado} for p in obj.participaciones_activas]

class CarreraCatalogoSerializer(serializers.ModelSerializer):
    class Meta: model=Carrera; fields=["slug","nombre"]

class AreaCatalogoSerializer(serializers.ModelSerializer):
    carreras=CarreraCatalogoSerializer(source="carreras_activas",many=True,read_only=True)
    class Meta: model=Area; fields=["slug","nombre","carreras"]

class PaseSerializer(serializers.ModelSerializer):
    rut=serializers.SerializerMethodField(); completos_disponibles=serializers.IntegerField(read_only=True)
    area_nombre=serializers.CharField(source="area.nombre",read_only=True,allow_null=True)
    carrera_nombre=serializers.CharField(source="carrera.nombre",read_only=True,allow_null=True)
    torneos=serializers.SerializerMethodField()
    class Meta:
        model=Asistente
        fields=["nombre","apellido","rut","area_nombre","carrera_nombre","codigo","completos_asignados","completos_retirados","completos_disponibles","torneos"]
    def get_rut(self,obj): return enmascarar_rut(obj.rut)
    def get_torneos(self,obj):
        result=[]
        participaciones=obj.participaciones.select_related("equipo__torneo","equipo__capitan").prefetch_related(
            "equipo__integrantes__asistente","equipo__cambios","equipo__torneo__partidas")
        for participation in participaciones:
            equipo=participation.equipo; torneo=equipo.torneo
            es_capitan=equipo.capitan_id==obj.pk
            puede_gestionar=autorizacion_gestion_capitan(equipo)[0] if es_capitan else False
            puede_reemplazar,motivo=autorizacion_reemplazo_capitan(equipo) if es_capitan else (False,None)
            item={"slug":torneo.slug,"nombre":torneo.nombre,"equipo_id":equipo.pk,"equipo":equipo.nombre,
                  "estado_equipo":equipo.estado,"posicion_espera":None,"es_capitan":es_capitan,
                  "torneo_estado":torneo.estado,"horario":f"{torneo.hora_inicio:%H:%M} – {torneo.hora_fin:%H:%M}",
                  "modalidad":torneo.modalidad,"inscripciones_abiertas":torneo.inscripciones_abiertas,
                  "llave_publicada":torneo.llave_publicada,"puede_gestionar":puede_gestionar,
                  "puede_reemplazar":puede_reemplazar,"motivo_no_reemplazo":None if puede_reemplazar else motivo,
                  "comodines_restantes":comodines_restantes_capitan(equipo) if es_capitan else None,
                  "integrantes":[{"id":x.pk,"nombre":x.asistente.nombre,"apellido":x.asistente.apellido,
                                  "gamertag":x.gamertag,"es_capitan":x.asistente_id==equipo.capitan_id}
                                 for x in equipo.integrantes.all()]}
            if equipo.estado=="espera": item["posicion_espera"]=torneo.equipos.filter(estado="espera",creado_en__lte=equipo.creado_en).count()
            result.append(item)
        return result

class RetiroSerializer(serializers.ModelSerializer):
    asistente=serializers.SerializerMethodField(); validado_por=serializers.SerializerMethodField()
    class Meta: model=RetiroCompleto; fields=["id","asistente","cantidad","validado_por","creado_en"]
    def get_asistente(self,obj):
        return {"nombre":obj.asistente.nombre,"apellido":obj.asistente.apellido,"codigo":obj.asistente.codigo}
    def get_validado_por(self,obj):
        if obj.validado_por is None: return None
        return obj.validado_por.get_full_name() or obj.validado_por.get_username()

class ConfiguracionEventoSerializer(serializers.ModelSerializer):
    aplicar_a_existentes=serializers.BooleanField(write_only=True,required=False,default=False)
    areas_prioritarias=serializers.SlugRelatedField(slug_field="slug",queryset=Area.objects.all(),many=True,required=False)
    class Meta:
        model=ConfiguracionEvento
        fields=["cupo_asistentes","registro_abierto","completos_por_asistente","mensaje_cupos_agotados","registro_restringido","restriccion_todos_los_tipos","areas_prioritarias","aplicar_a_existentes"]
