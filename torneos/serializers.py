from django.db import transaction
from rest_framework import serializers
from evento.models import Asistente
from evento.validators import normalizar_rut
from .models import Equipo, Integrante, Partida, Torneo

class IntegrantePublicoSerializer(serializers.ModelSerializer):
    nombre=serializers.SerializerMethodField()
    class Meta: model=Integrante; fields=["nombre","gamertag"]
    def get_nombre(self,o): return f"{o.asistente.nombre} {o.asistente.apellido}"
class EquipoPublicoSerializer(serializers.ModelSerializer):
    integrantes=IntegrantePublicoSerializer(many=True,read_only=True)
    class Meta: model=Equipo; fields=["id","nombre","integrantes","seed"]
class TorneoSerializer(serializers.ModelSerializer):
    equipos_confirmados=serializers.IntegerField(read_only=True); cupos_disponibles=serializers.IntegerField(read_only=True); inscripciones_abiertas=serializers.BooleanField(read_only=True)
    class Meta: model=Torneo; fields=["nombre","slug","juego","modalidad","jugadores_por_equipo","cupo_equipos","estado","hora_inicio","hora_fin","reglas","cierre_inscripciones","equipos_confirmados","cupos_disponibles","inscripciones_abiertas"]
class TorneoDetalleSerializer(TorneoSerializer):
    equipos=serializers.SerializerMethodField()
    class Meta(TorneoSerializer.Meta): fields=TorneoSerializer.Meta.fields+["equipos"]
    def get_equipos(self,o): return EquipoPublicoSerializer(o.equipos.filter(estado="confirmado"),many=True).data
class InscripcionSerializer(serializers.Serializer):
    nombre_equipo=serializers.CharField(max_length=80); integrantes=serializers.ListField(child=serializers.DictField())
    def validate(self,data):
        torneo=self.context["torneo"]
        if not torneo.inscripciones_abiertas: raise serializers.ValidationError("Las inscripciones no están abiertas.")
        if len(data["integrantes"])!=torneo.jugadores_por_equipo: raise serializers.ValidationError(f"Se requieren exactamente {torneo.jugadores_por_equipo} integrantes.")
        attendees=[]; seen=set()
        for member in data["integrantes"]:
            try: rut=normalizar_rut(member.get("rut",""))
            except Exception: raise serializers.ValidationError(f"RUT {member.get('rut','')} inválido.")
            attendee=Asistente.objects.filter(rut=rut).first()
            if not attendee: raise serializers.ValidationError(f"El RUT {rut} no está registrado; debe registrarse primero al evento.")
            if attendee.pk in seen or Integrante.objects.filter(equipo__torneo=torneo,asistente=attendee).exists(): raise serializers.ValidationError(f"El asistente con RUT {rut} ya participa en un equipo de este torneo.")
            seen.add(attendee.pk); attendees.append((attendee,member.get("gamertag","")))
        data["attendees"]=attendees; return data
    @transaction.atomic
    def create(self,data):
        torneo=Torneo.objects.select_for_update().get(pk=self.context["torneo"].pk)
        state="confirmado" if torneo.cupos_disponibles>0 else "espera"
        equipo=Equipo.objects.create(torneo=torneo,nombre=data["nombre_equipo"],capitan=data["attendees"][0][0],estado=state)
        Integrante.objects.bulk_create([Integrante(equipo=equipo,asistente=a,gamertag=g) for a,g in data["attendees"]])
        return equipo
class PartidaSerializer(serializers.ModelSerializer):
    equipo_a=EquipoPublicoSerializer(read_only=True); equipo_b=EquipoPublicoSerializer(read_only=True); ganador=EquipoPublicoSerializer(read_only=True)
    class Meta: model=Partida; fields=["id","ronda","orden","equipo_a","equipo_b","score_a","score_b","ganador","estado","siguiente_partida","slot_siguiente"]
