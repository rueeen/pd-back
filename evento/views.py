from django.db.models import Count, F, Q, Sum
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView
from .models import Asistente, RetiroCompleto
from .serializers import AsistenteSerializer, PaseSerializer, RetiroSerializer
from .services import registrar_retiro
from .validators import normalizar_rut

class RegistrationThrottle(AnonRateThrottle): scope="registration"
class RegistroView(APIView):
    permission_classes=[AllowAny]; throttle_classes=[RegistrationThrottle]
    def post(self,request):
        try: rut=normalizar_rut(request.data.get("rut",""))
        except Exception: rut=request.data.get("rut","")
        existing=Asistente.objects.filter(rut=rut).first()
        if existing: return Response(AsistenteSerializer(existing).data)
        s=AsistenteSerializer(data=request.data); s.is_valid(raise_exception=True)
        return Response(AsistenteSerializer(s.save()).data,status=status.HTTP_201_CREATED)
class PaseView(APIView):
    permission_classes=[AllowAny]
    def get(self,request,codigo): return Response(PaseSerializer(get_object_or_404(Asistente,codigo=codigo.upper())).data)
class AdminAsistentesView(APIView):
    permission_classes=[IsAuthenticated]
    def get(self,request):
        qs=Asistente.objects.all().order_by("-creado_en"); q=request.query_params.get("q")
        if q: qs=qs.filter(Q(nombre__icontains=q)|Q(apellido__icontains=q)|Q(rut__icontains=q)|Q(codigo__icontains=q))
        if request.query_params.get("con_saldo")=="1": qs=qs.filter(completos_retirados__lt=F("completos_asignados"))
        return Response(AsistenteSerializer(qs,many=True).data)
class AdminAsistenteView(APIView):
    permission_classes=[IsAuthenticated]
    def get(self,request,codigo): return Response(AsistenteSerializer(get_object_or_404(Asistente,codigo=codigo.upper())).data)
class AdminRetirosView(APIView):
    permission_classes=[IsAuthenticated]
    def get(self,request): return Response(RetiroSerializer(RetiroCompleto.objects.all(),many=True).data)
    def post(self,request):
        attendee=get_object_or_404(Asistente,codigo=str(request.data.get("codigo","")).upper())
        try: retiro=registrar_retiro(attendee,request.data.get("cantidad"),request.user)
        except Exception as exc: raise ValidationError(exc.messages if hasattr(exc,"messages") else str(exc))
        return Response(RetiroSerializer(retiro).data,status=201)
class AdminResumenView(APIView):
    permission_classes=[IsAuthenticated]
    def get(self,request):
        from torneos.models import Torneo
        return Response({"total_registrados":Asistente.objects.count(),"completos_entregados":RetiroCompleto.objects.aggregate(v=Sum("cantidad"))["v"] or 0,"completos_pendientes":Asistente.objects.aggregate(v=Sum(F("completos_asignados")-F("completos_retirados")))["v"] or 0,"inscritos_por_torneo":{t.slug:t.equipos.filter(estado="confirmado").count() for t in Torneo.objects.all()},"aportes_comprometidos":{x["aporte"]:x["total"] for x in Asistente.objects.values("aporte").annotate(total=Count("id"))}})
