from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import Equipo, Partida, Torneo
from .serializers import *
from .services import generar_bracket, registrar_resultado
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
        t=get_object_or_404(Torneo,slug=slug); matches=PartidaSerializer(t.partidas.all(),many=True).data
        return Response({"torneo":t.nombre,"rondas":[{"ronda":n,"partidas":[x for x in matches if x["ronda"]==n]} for n in sorted({x["ronda"] for x in matches})]})
class SorteoView(APIView):
    permission_classes=[IsAuthenticated]
    def post(self,r,slug):
        try: t=generar_bracket(get_object_or_404(Torneo,slug=slug))
        except Exception as e: raise ValidationError(e.messages if hasattr(e,"messages") else str(e))
        return Response({"estado":t.estado,"partidas":t.partidas.count()})
class ResultadoView(APIView):
    permission_classes=[IsAuthenticated]
    def patch(self,r,pk):
        try: p=registrar_resultado(get_object_or_404(Partida,pk=pk),int(r.data["score_a"]),int(r.data["score_b"]),r.user)
        except (KeyError,TypeError,ValueError): raise ValidationError("score_a y score_b deben ser enteros.")
        except Exception as e: raise ValidationError(e.messages if hasattr(e,"messages") else str(e))
        return Response(PartidaSerializer(p).data)
class EquipoAdminView(APIView):
    permission_classes=[IsAuthenticated]
    def patch(self,r,pk):
        team=get_object_or_404(Equipo,pk=pk); state=r.data.get("estado")
        if state not in dict(Equipo.ESTADOS): raise ValidationError("Estado inválido.")
        team.estado=state; team.save(update_fields=["estado"]); return Response({"id":team.pk,"estado":team.estado})
