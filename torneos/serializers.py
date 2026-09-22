from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from rest_framework import serializers
from evento.models import Asistente
from evento.validators import normalizar_rut
from .models import CambioIntegrante, Equipo, Integrante, Partida, Torneo

class IntegrantePublicoSerializer(serializers.ModelSerializer):
    nombre=serializers.SerializerMethodField()
    class Meta: model=Integrante; fields=["nombre","gamertag"]
    def get_nombre(self,o): return f"{o.asistente.nombre} {o.asistente.apellido}"
class EquipoPublicoSerializer(serializers.ModelSerializer):
    integrantes=IntegrantePublicoSerializer(many=True,read_only=True)
    class Meta: model=Equipo; fields=["id","nombre","integrantes","seed"]
class AsistenteAdminSerializer(serializers.ModelSerializer):
    class Meta: model=Asistente; fields=["nombre","apellido","codigo"]
class IntegranteAdminSerializer(serializers.ModelSerializer):
    nombre=serializers.CharField(source="asistente.nombre",read_only=True)
    apellido=serializers.CharField(source="asistente.apellido",read_only=True)
    codigo=serializers.CharField(source="asistente.codigo",read_only=True)
    rut=serializers.CharField(source="asistente.rut",read_only=True)
    es_capitan=serializers.SerializerMethodField(); es_comodin=serializers.SerializerMethodField()
    class Meta: model=Integrante; fields=["nombre","apellido","rut","codigo","gamertag","es_capitan","es_comodin"]
    def get_es_capitan(self,o): return o.equipo.capitan_id==o.asistente_id
    def get_es_comodin(self,o): return any(c.entrante_id==o.asistente_id for c in o.equipo.cambios.all())
class CambioIntegranteSerializer(serializers.ModelSerializer):
    saliente=serializers.SerializerMethodField(); entrante=serializers.SerializerMethodField()
    motivo_display=serializers.CharField(source="get_motivo_display",read_only=True)
    realizado_por=serializers.SerializerMethodField()
    class Meta: model=CambioIntegrante; fields=["saliente","entrante","motivo","motivo_display","detalle","realizado_por","creado_en"]
    def get_saliente(self,o): return f"{o.saliente.nombre} {o.saliente.apellido}"
    def get_entrante(self,o): return f"{o.entrante.nombre} {o.entrante.apellido}"
    def get_realizado_por(self,o):
        return (o.realizado_por.get_full_name() or o.realizado_por.get_username()) if o.realizado_por else None
class EquipoAdminSerializer(serializers.ModelSerializer):
    capitan=AsistenteAdminSerializer(read_only=True)
    integrantes=IntegranteAdminSerializer(many=True,read_only=True)
    cambios=CambioIntegranteSerializer(many=True,read_only=True)
    class Meta: model=Equipo; fields=["id","nombre","acreditado","capitan","integrantes","cambios"]
class TorneoSerializer(serializers.ModelSerializer):
    equipos_confirmados=serializers.IntegerField(read_only=True); cupos_disponibles=serializers.IntegerField(read_only=True); inscripciones_abiertas=serializers.BooleanField(read_only=True)
    class Meta: model=Torneo; fields=["nombre","slug","juego","modalidad","jugadores_por_equipo","cupo_equipos","estado","bloque","equipamiento","hora_inicio","hora_fin","reglas","cierre_inscripciones","equipos_confirmados","cupos_disponibles","inscripciones_abiertas"]
class TorneoDetalleSerializer(TorneoSerializer):
    equipos=serializers.SerializerMethodField()
    class Meta(TorneoSerializer.Meta): fields=TorneoSerializer.Meta.fields+["equipos"]
    def get_equipos(self,o): return EquipoPublicoSerializer(o.equipos.filter(estado="confirmado"),many=True).data
class InscripcionSerializer(serializers.Serializer):
    nombre_equipo=serializers.CharField(max_length=80); integrantes=serializers.ListField(child=serializers.DictField())
    def validate(self,data):
        torneo=self.context["torneo"]
        if not torneo.inscripciones_abiertas: raise serializers.ValidationError("Las inscripciones no están abiertas.")
        data["nombre_equipo"]=data["nombre_equipo"].strip()
        if Equipo.objects.filter(torneo=torneo,nombre__iexact=data["nombre_equipo"]).exists():
            raise serializers.ValidationError({"nombre_equipo":"El nombre ya está tomado en ese torneo, elige otro."})
        if len(data["integrantes"])!=torneo.jugadores_por_equipo: raise serializers.ValidationError(f"Se requieren exactamente {torneo.jugadores_por_equipo} integrantes.")
        attendees=[]; seen=set()
        for member in data["integrantes"]:
            try: rut=normalizar_rut(member.get("rut",""))
            except DjangoValidationError: raise serializers.ValidationError(f"RUT {member.get('rut','')} inválido.")
            attendee=Asistente.objects.filter(rut=rut).first()
            if not attendee: raise serializers.ValidationError(f"El RUT {rut} no está registrado; debe registrarse primero al evento.")
            if attendee.pk in seen or Integrante.objects.filter(equipo__torneo=torneo,asistente=attendee).exclude(equipo__estado="retirado").exists(): raise serializers.ValidationError(f"El asistente con RUT {rut} ya participa en un equipo de este torneo.")
            conflicto=(Integrante.objects.select_related("equipo__torneo")
                       .filter(asistente=attendee,equipo__torneo__bloque=torneo.bloque)
                       .exclude(equipo__torneo=torneo).exclude(equipo__estado="retirado").first()
                       if torneo.bloque else None)
            if conflicto:
                raise serializers.ValidationError(f"El asistente con RUT {rut} ya participa en {conflicto.equipo.torneo.nombre}, que se juega en el mismo bloque.")
            seen.add(attendee.pk); attendees.append((attendee,member.get("gamertag","")))
        data["attendees"]=attendees; return data
    @transaction.atomic
    def create(self,data):
        torneo=Torneo.objects.select_for_update().get(pk=self.context["torneo"].pk)
        state="confirmado" if torneo.cupos_disponibles>0 else "espera"
        try:
            equipo=Equipo.objects.create(torneo=torneo,nombre=data["nombre_equipo"],capitan=data["attendees"][0][0],estado=state)
        except IntegrityError:
            raise serializers.ValidationError({"nombre_equipo":"El nombre ya está tomado en ese torneo, elige otro."})
        Integrante.objects.bulk_create([Integrante(equipo=equipo,asistente=a,gamertag=g) for a,g in data["attendees"]])
        return equipo
class PartidaSerializer(serializers.ModelSerializer):
    equipo_a=EquipoPublicoSerializer(read_only=True); equipo_b=EquipoPublicoSerializer(read_only=True); ganador=EquipoPublicoSerializer(read_only=True)
    bye=serializers.SerializerMethodField(); es_final=serializers.SerializerMethodField()
    class Meta: model=Partida; fields=["id","ronda","orden","equipo_a","equipo_b","score_a","score_b","ganador","estado","por_walkover","siguiente_partida","slot_siguiente","bye","es_final"]
    def get_bye(self,obj): return obj.estado=="finalizada" and bool(obj.ganador_id) and not (obj.equipo_a_id and obj.equipo_b_id)
    def get_es_final(self,obj): return obj.siguiente_partida_id is None
