from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import Equipo, Partida, Torneo
from .serializers import *
from .services import generar_bracket, registrar_resultado

def _nombre_ronda(numero,total):
    distancia=total-numero
    if distancia==0: return "Final"
    if distancia==1: return "Semifinal"
    if distancia==2: return "Cuartos de final"
    return f"Ronda {numero}"

def _datos_bracket(torneo):
    matches=PartidaSerializer(torneo.partidas.all(),many=True).data
    rondas=sorted({x["ronda"] for x in matches}); total=max(rondas,default=0)
    equipos=lambda estado: list(torneo.equipos.filter(estado=estado).values("id","nombre"))
    return {"torneo":torneo.nombre,"slug":torneo.slug,"estado":torneo.estado,
            "horario":f"{torneo.hora_inicio:%H:%M} – {torneo.hora_fin:%H:%M}",
            "equipos_confirmados":equipos("confirmado"),"equipos_espera":equipos("espera"),
            "rondas":[{"ronda":n,"nombre":_nombre_ronda(n,total),"partidas":[x for x in matches if x["ronda"]==n]} for n in rondas]}
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
        return Response(_datos_bracket(get_object_or_404(Torneo,slug=slug)))
class TorneoAdminView(APIView):
    permission_classes=[IsAuthenticated]
    def get(self,r,slug): return Response(_datos_bracket(get_object_or_404(Torneo,slug=slug)))
class SorteoView(APIView):
    permission_classes=[IsAuthenticated]
    def post(self,r,slug):
        try: t=generar_bracket(get_object_or_404(Torneo,slug=slug))
        except DjangoValidationError as e: raise ValidationError(e.messages)
        return Response({"estado":t.estado,"partidas":t.partidas.count()})
class ResultadoView(APIView):
    permission_classes=[IsAuthenticated]
    def patch(self,r,pk):
        try: p=registrar_resultado(get_object_or_404(Partida,pk=pk),int(r.data["score_a"]),int(r.data["score_b"]),r.user,reabrir=r.data.get("reabrir") is True)
        except (KeyError,TypeError,ValueError): raise ValidationError("score_a y score_b deben ser enteros.")
        except DjangoValidationError as e: raise ValidationError(e.messages)
        return Response(PartidaSerializer(p).data)
class EquipoAdminView(APIView):
    permission_classes=[IsAuthenticated]
    def patch(self,r,pk):
        team=get_object_or_404(Equipo,pk=pk); state=r.data.get("estado")
        if state not in dict(Equipo.ESTADOS): raise ValidationError("Estado inválido.")
        team.estado=state; team.save(update_fields=["estado"]); return Response({"id":team.pk,"estado":team.estado})
