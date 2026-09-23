from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Q
import math
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from evento.models import Asistente
from evento.validators import normalizar_rut
from evento.views import ExplainedAnonRateThrottle
from .models import Equipo, Integrante, Partida, PromocionEspera, Torneo
from .serializers import *
from .services import (autorizacion_gestion_capitan, autorizacion_reemplazo_capitan,
                       comodines_restantes_capitan, generar_bracket, MAX_COMODINES_CAPITAN,
                       registrar_resultado, reemplazar_integrante)

class TeamManagementThrottle(ExplainedAnonRateThrottle): scope="team_management"

def _validation_error(detail):
    """Build the consistent error envelope used by tournament administration."""
    return ValidationError({"detail":detail})

def _nombre_ronda(numero,total):
    distancia=total-numero
    if distancia==0: return "Final"
    if distancia==1: return "Semifinal"
    if distancia==2: return "Cuartos de final"
    return f"Ronda {numero}"

def _datos_bracket(torneo,admin=False):
    matches=PartidaSerializer(torneo.partidas.all(),many=True).data
    rondas=sorted({x["ronda"] for x in matches}); total=max(rondas,default=0)
    equipos=lambda estado: (EquipoAdminSerializer(torneo.equipos.filter(estado=estado).select_related("capitan").prefetch_related(
                                "integrantes__asistente","cambios__saliente","cambios__entrante","cambios__realizado_por"),many=True).data
                            if admin else list(torneo.equipos.filter(estado=estado).values("id","nombre")))
    return {"torneo":torneo.nombre,"slug":torneo.slug,"estado":torneo.estado,
            "modalidad":torneo.modalidad,"jugadores_por_equipo":torneo.jugadores_por_equipo,
            "horario":f"{torneo.hora_inicio:%H:%M} – {torneo.hora_fin:%H:%M}",
            "equipos_confirmados":equipos("confirmado"),"equipos_espera":equipos("espera"),
            "rondas":[{"ronda":n,"nombre":_nombre_ronda(n,total),"total_partidas":sum(x["ronda"]==n for x in matches),
                       "partidas":[x for x in matches if x["ronda"]==n]} for n in rondas]}

def _demanda_primera_ronda(torneo):
    potencia=2**int(math.floor(math.log2(torneo.cupo_equipos)))
    equipos=torneo.cupo_equipos if potencia==torneo.cupo_equipos else 2*(torneo.cupo_equipos-potencia)
    return equipos*torneo.jugadores_por_equipo

class TorneosView(APIView):
    permission_classes=[AllowAny]
    def get(self,r): return Response(TorneoSerializer(Torneo.objects.all(),many=True).data)
class TorneoView(APIView):
    permission_classes=[AllowAny]
    def get(self,r,slug): return Response(TorneoDetalleSerializer(get_object_or_404(Torneo,slug=slug)).data)
class InscripcionView(APIView):
    permission_classes=[AllowAny]
    def post(self,r,slug):
        torneo=get_object_or_404(Torneo,slug=slug); s=InscripcionSerializer(data=r.data,context={"torneo":torneo}); s.is_valid(raise_exception=True); team=s.save()
        data=EquipoPublicoSerializer(team).data|{"estado":team.estado}
        if team.estado=="espera": data|={"mensaje":"Equipo inscrito en lista de espera.","posicion_espera":Equipo.objects.filter(torneo=torneo,estado="espera",creado_en__lte=team.creado_en).count()}
        return Response(data,status=201)
class BracketView(APIView):
    permission_classes=[AllowAny]
    def get(self,r,slug):
        torneo=get_object_or_404(Torneo,slug=slug)
        if not torneo.llave_publicada:
            return Response({"torneo":torneo.nombre,"slug":torneo.slug,"estado":torneo.estado,
                             "modalidad":torneo.modalidad,"jugadores_por_equipo":torneo.jugadores_por_equipo,
                             "horario":f"{torneo.hora_inicio:%H:%M} – {torneo.hora_fin:%H:%M}",
                             "total_inscritos":torneo.equipos.exclude(estado="retirado").count(),
                             "cupo_equipos":torneo.cupo_equipos,"rondas":[]})
        return Response(_datos_bracket(torneo))
class TorneoAdminView(APIView):
    permission_classes=[IsAuthenticated]
    def get(self,r,slug): return Response(_datos_bracket(get_object_or_404(Torneo,slug=slug),admin=True))
    @transaction.atomic
    def patch(self,r,slug):
        torneo=get_object_or_404(Torneo.objects.select_for_update(),slug=slug)
        fields=[]; promovidos=[]
        if "llave_publicada" in r.data:
            if not isinstance(r.data["llave_publicada"],bool):
                raise _validation_error("Debe indicar un booleano para llave_publicada.")
            torneo.llave_publicada=r.data["llave_publicada"]; fields.append("llave_publicada")
            if not torneo.llave_publicada and torneo.estado=="sorteado":
                torneo.estado="cerrado"; fields.append("estado")
        if "cierre_inscripciones" in r.data:
            from django.utils.dateparse import parse_datetime
            cierre=parse_datetime(str(r.data["cierre_inscripciones"]))
            if cierre is None: raise _validation_error("Ingrese una fecha y hora válidas para cierre_inscripciones.")
            if timezone.is_naive(cierre): cierre=timezone.make_aware(cierre)
            if torneo.estado!="inscripcion":
                raise _validation_error("El plazo solo puede extenderse durante las inscripciones.")
            if cierre<=torneo.cierre_inscripciones:
                raise _validation_error("La nueva fecha debe ser posterior al cierre actual.")
            torneo.cierre_inscripciones=cierre; fields.append("cierre_inscripciones")
        if "cupo_equipos" in r.data:
            if torneo.estado!="inscripcion":
                return Response({"detail":"El cupo solo puede ampliarse mientras el torneo está en inscripción."},status=400)
            try: nuevo=int(r.data["cupo_equipos"])
            except (TypeError,ValueError): raise _validation_error("cupo_equipos debe ser un entero positivo.")
            if nuevo < 1: raise _validation_error("cupo_equipos debe ser un entero positivo.")
            anterior=torneo.cupo_equipos; torneo.cupo_equipos=nuevo; fields.append("cupo_equipos")
            if nuevo<=anterior:
                return Response({"detail":"El nuevo cupo debe ser mayor al cupo actual."},status=400)
            confirmados=torneo.equipos.filter(estado="confirmado").count()
            espera=list(torneo.equipos.select_for_update().select_related("capitan").filter(estado="espera").order_by("creado_en","pk")[:nuevo-confirmados])
            for equipo in espera:
                equipo.estado="confirmado"; equipo.save(update_fields=["estado"])
                PromocionEspera.objects.create(torneo=torneo,equipo=equipo)
                promovidos.append({"id":equipo.pk,"nombre":equipo.nombre,"capitan":f"{equipo.capitan.nombre} {equipo.capitan.apellido}"})
        if not fields: raise _validation_error("Debe indicar cupo_equipos, cierre_inscripciones o llave_publicada.")
        torneo.save(update_fields=list(dict.fromkeys(fields)))
        data={"slug":torneo.slug,"cupo_equipos":torneo.cupo_equipos,"cierre_inscripciones":torneo.cierre_inscripciones,
              "llave_publicada":torneo.llave_publicada,"equipos_promovidos":promovidos}
        if "cupo_equipos" in r.data:
            demanda=sum(_demanda_primera_ronda(t) for t in Torneo.objects.filter(bloque=torneo.bloque,equipamiento=torneo.equipamiento))
            if demanda>20:
                data["advertencia"]=f"El bloque y equipamiento asignados requieren {demanda} estaciones simultáneas y exceden las 20 disponibles."
        return Response(data)

class CerrarInscripcionesView(APIView):
    permission_classes=[IsAuthenticated]
    def post(self,r,slug):
        torneo=get_object_or_404(Torneo,slug=slug)
        if torneo.estado!="inscripcion":
            return Response({"detail":"Solo se pueden cerrar inscripciones desde el estado inscripción."},status=400)
        torneo.estado="cerrado"; torneo.save(update_fields=["estado"])
        return Response({"slug":torneo.slug,"estado":torneo.estado})

class ReabrirInscripcionesView(APIView):
    permission_classes=[IsAuthenticated]
    def post(self,r,slug):
        torneo=get_object_or_404(Torneo,slug=slug)
        if torneo.estado in ("sorteado","en_curso","finalizado") or torneo.llave_publicada:
            return Response({"detail":"Primero debes despublicar la llave antes de reabrir las inscripciones."},status=400)
        if torneo.estado!="cerrado":
            return Response({"detail":"Solo se pueden reabrir inscripciones desde el estado cerrado."},status=400)
        torneo.estado="inscripcion"; torneo.save(update_fields=["estado"])
        return Response({"slug":torneo.slug,"estado":torneo.estado})
class SorteoView(APIView):
    permission_classes=[IsAuthenticated]
    def post(self,r,slug):
        solo_acreditados=r.data.get("solo_acreditados",False)
        if not isinstance(solo_acreditados,bool): raise _validation_error("solo_acreditados debe ser un booleano.")
        try: t=generar_bracket(get_object_or_404(Torneo,slug=slug),solo_acreditados=solo_acreditados)
        except DjangoValidationError as e: return Response({"detail":e.messages[0]},status=status.HTTP_400_BAD_REQUEST)
        return Response({"estado":t.estado,"partidas":t.partidas.count()})
class ResultadoView(APIView):
    permission_classes=[IsAuthenticated]
    def patch(self,r,pk):
        walkover=r.data.get("walkover")
        if "walkover" in r.data and ("score_a" in r.data or "score_b" in r.data):
            raise _validation_error("walkover y los marcadores son formas excluyentes de cerrar una partida.")
        try:
            if "walkover" in r.data:
                p=registrar_resultado(get_object_or_404(Partida,pk=pk),usuario=r.user,reabrir=r.data.get("reabrir") is True,walkover=walkover)
            else:
                p=registrar_resultado(get_object_or_404(Partida,pk=pk),int(r.data["score_a"]),int(r.data["score_b"]),r.user,reabrir=r.data.get("reabrir") is True)
        except (KeyError,TypeError,ValueError): raise _validation_error("score_a y score_b deben ser enteros.")
        except DjangoValidationError as e: raise _validation_error(e.messages[0])
        return Response(PartidaSerializer(p).data)
class EquipoAdminView(APIView):
    permission_classes=[IsAuthenticated]
    @transaction.atomic
    def patch(self,r,pk):
        team=get_object_or_404(Equipo.objects.select_for_update().select_related("torneo"),pk=pk); fields=[]
        if "estado" in r.data:
            state=r.data["estado"]
            if state not in dict(Equipo.ESTADOS): raise _validation_error("Estado inválido.")
            team.estado=state; fields.append("estado")
        if "acreditado" in r.data:
            acreditado=r.data["acreditado"]
            if not isinstance(acreditado,bool): raise _validation_error("acreditado debe ser un booleano.")
            team.acreditado=acreditado; team.acreditado_en=timezone.now() if acreditado else None
            fields.extend(["acreditado","acreditado_en"])
        if "nombre" in r.data:
            nombre=str(r.data["nombre"]).strip()
            if not nombre: raise _validation_error("El nombre del equipo no puede estar vacío.")
            if Equipo.objects.filter(torneo=team.torneo,nombre__iexact=nombre).exclude(pk=team.pk).exists():
                raise _validation_error("El nombre ya está tomado en ese torneo, elige otro.")
            team.nombre=nombre; fields.append("nombre")
        if "capitan_rut" in r.data:
            try: rut=normalizar_rut(r.data["capitan_rut"])
            except DjangoValidationError as e: raise _validation_error(e.messages[0])
            integrante=team.integrantes.select_related("asistente").filter(asistente__rut=rut).first()
            if not integrante: raise _validation_error("El nuevo capitán debe ser integrante del equipo.")
            team.capitan=integrante.asistente; fields.append("capitan")
        if not fields: raise _validation_error("Debe indicar estado, acreditado, nombre o capitan_rut.")
        team.save(update_fields=fields)
        return Response({"id":team.pk,"estado":team.estado,"acreditado":team.acreditado,"acreditado_en":team.acreditado_en,
                         "nombre":team.nombre,"capitan_rut":team.capitan.rut})

class ReemplazoIntegranteView(APIView):
    permission_classes=[IsAuthenticated]
    def post(self,r,pk):
        equipo=get_object_or_404(Equipo,pk=pk)
        forzar=r.data.get("forzar",False)
        if not isinstance(forzar,bool): raise _validation_error("forzar debe ser un booleano.")
        faltantes=[campo for campo in ("rut_saliente","rut_entrante","motivo") if campo not in r.data]
        if faltantes: raise _validation_error(f"Debe indicar {', '.join(faltantes)}.")
        try:
            equipo=reemplazar_integrante(equipo,r.data["rut_saliente"],r.data["rut_entrante"],r.user,r.data["motivo"],
                                         r.data.get("detalle",""),r.data.get("gamertag",""),r.data.get("nombre_equipo"),forzar)
        except DjangoValidationError as e: raise _validation_error(e.messages[0])
        equipo=Equipo.objects.select_related("capitan").prefetch_related(
            "integrantes__asistente","cambios__saliente","cambios__entrante","cambios__realizado_por").get(pk=equipo.pk)
        return Response(EquipoAdminSerializer(equipo).data)

class CandidatosComodinView(APIView):
    permission_classes=[IsAuthenticated]
    def get(self,r,slug):
        torneo=get_object_or_404(Torneo,slug=slug); q=str(r.query_params.get("q","")).strip()
        if len(q)<2: return Response([])
        ocupados=Integrante.objects.filter(equipo__torneo=torneo).exclude(equipo__estado="retirado").values_list("asistente_id",flat=True)
        candidatos=list(Asistente.objects.select_related("carrera").filter(
            Q(nombre__icontains=q)|Q(apellido__icontains=q)|Q(rut__icontains=q)|Q(codigo__icontains=q)
        ).exclude(pk__in=ocupados).order_by("apellido","nombre")[:20])
        conflictos={}
        if torneo.bloque:
            participaciones=(Integrante.objects.select_related("equipo__torneo").filter(
                asistente_id__in=[a.pk for a in candidatos],equipo__torneo__bloque=torneo.bloque
            ).exclude(equipo__torneo=torneo).exclude(equipo__estado="retirado").order_by("pk"))
            for integrante in participaciones: conflictos.setdefault(integrante.asistente_id,integrante.equipo.torneo.nombre)
        return Response([{"rut":a.rut,"nombre":a.nombre,"apellido":a.apellido,"codigo":a.codigo,"tipo":a.tipo,
                          "carrera_nombre":a.carrera.nombre if a.carrera else None,"conflicto_bloque":conflictos.get(a.pk)} for a in candidatos])

def _autorizar_capitan(equipo,data):
    codigo=str(data.get("codigo_capitan","")).upper()
    if not codigo or codigo!=equipo.capitan.codigo.upper():
        return Response({"detail":"El código no corresponde al capitán del equipo."},status=status.HTTP_403_FORBIDDEN)
    permitido,motivo=autorizacion_gestion_capitan(equipo)
    if not permitido: return Response({"detail":motivo},status=status.HTTP_400_BAD_REQUEST)

def _autorizar_reemplazo_capitan(equipo,data):
    codigo=str(data.get("codigo_capitan","")).upper()
    if not codigo or codigo!=equipo.capitan.codigo.upper():
        return Response({"detail":"El código no corresponde al capitán del equipo."},status=status.HTTP_403_FORBIDDEN)
    permitido,motivo=autorizacion_reemplazo_capitan(equipo)
    if not permitido: return Response({"detail":motivo},status=status.HTTP_400_BAD_REQUEST)

class EquipoCapitanView(APIView):
    permission_classes=[AllowAny]
    throttle_classes=[TeamManagementThrottle]
    def patch(self,r,pk):
        equipo=get_object_or_404(Equipo.objects.select_related("capitan","torneo"),pk=pk)
        error=_autorizar_capitan(equipo,r.data)
        if error: return error
        nombre=str(r.data.get("nombre_equipo","")).strip()
        if not nombre: raise ValidationError({"nombre_equipo":"Este campo es obligatorio."})
        if Equipo.objects.filter(torneo=equipo.torneo,nombre__iexact=nombre).exclude(pk=equipo.pk).exists():
            raise ValidationError({"nombre_equipo":"El nombre ya está tomado en ese torneo, elige otro."})
        equipo.nombre=nombre; equipo.save(update_fields=["nombre"])
        return Response({"id":equipo.pk,"nombre_equipo":equipo.nombre})
    @transaction.atomic
    def delete(self,r,pk):
        equipo=get_object_or_404(Equipo.objects.select_for_update().select_related("capitan","torneo"),pk=pk)
        error=_autorizar_capitan(equipo,r.data)
        if error: return error
        ocupaba_cupo=equipo.estado=="confirmado"; equipo.estado="retirado"; equipo.save(update_fields=["estado"])
        promovido=None
        if ocupaba_cupo:
            promovido=Equipo.objects.select_for_update().filter(torneo=equipo.torneo,estado="espera").order_by("creado_en","pk").first()
            if promovido:
                promovido.estado="confirmado"; promovido.save(update_fields=["estado"])
                PromocionEspera.objects.create(torneo=equipo.torneo,equipo=promovido)
        return Response({"id":equipo.pk,"estado":"retirado","equipo_promovido_id":promovido.pk if promovido else None})

class EquipoIntegrantesView(APIView):
    permission_classes=[AllowAny]
    throttle_classes=[TeamManagementThrottle]
    @transaction.atomic
    def post(self,r,pk):
        equipo=get_object_or_404(Equipo.objects.select_for_update().select_related("capitan","torneo"),pk=pk)
        error=_autorizar_reemplazo_capitan(equipo,r.data)
        if error: return error
        if "integrante_id" in r.data:
            integrante=get_object_or_404(Integrante.objects.select_related("asistente"),pk=r.data["integrante_id"],equipo=equipo)
            saliente=integrante.asistente.rut
        else:
            try: saliente=normalizar_rut(r.data.get("rut_saliente",""))
            except DjangoValidationError as exc: raise ValidationError({"detail":exc.messages[0]})
            integrante=get_object_or_404(Integrante.objects.select_related("asistente"),equipo=equipo,asistente__rut=saliente)
        try: entrante=normalizar_rut(r.data.get("rut_entrante",""))
        except DjangoValidationError as exc: raise ValidationError({"detail":exc.messages[0]})
        if saliente==equipo.capitan.rut: raise ValidationError({"detail":"El capitán no puede sacarse a sí mismo; debe retirar el equipo completo."})
        nuevo=Asistente.objects.filter(rut=entrante).first()
        if equipo.torneo.estado!="inscripcion" and (not nuevo or str(r.data.get("codigo_entrante","")).upper()!=nuevo.codigo.upper()):
            raise ValidationError({"detail":"El RUT y el código del comodín no coinciden."})
        try:
            reemplazar_integrante(equipo,saliente,entrante,None,r.data.get("motivo","no_se_presento"),
                                  r.data.get("detalle",""),r.data.get("gamertag",""),forzar=False,origen="capitan")
        except DjangoValidationError as exc: raise ValidationError({"detail":exc.messages[0]})
        return Response({"equipo_id":equipo.pk,"rut_saliente":saliente,"rut_entrante":entrante,
                         "gamertag":str(r.data.get("gamertag","")).strip(),
                         "comodines_restantes":comodines_restantes_capitan(equipo)})
