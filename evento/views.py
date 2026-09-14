from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Count, F, Prefetch, Q, Sum
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView
from .models import Area, Asistente, Carrera, RetiroCompleto
from .serializers import AreaCatalogoSerializer, AsistenteSerializer, PaseSerializer, RetiroSerializer
from .services import registrar_retiro
from .validators import normalizar_rut

class RegistrationThrottle(AnonRateThrottle): scope="registration"
class CatalogoAreasView(APIView):
    permission_classes=[AllowAny]
    throttle_classes=[]
    def get(self,request):
        qs=Area.objects.filter(activa=True).prefetch_related(
            Prefetch("carreras",queryset=Carrera.objects.filter(activa=True),to_attr="carreras_activas")
        )
        return Response(AreaCatalogoSerializer(qs,many=True).data)
class RegistroView(APIView):
    permission_classes=[AllowAny]; throttle_classes=[RegistrationThrottle]
    def post(self,request):
        try: rut=normalizar_rut(request.data.get("rut",""))
        except DjangoValidationError: rut=request.data.get("rut","")
        existing=Asistente.objects.filter(rut=rut).first()
        if existing:
            supplied_email=str(request.data.get("email","")).strip()
            if not supplied_email or supplied_email.casefold() != existing.email.strip().casefold():
                return Response({"detail":"Ese RUT ya está registrado. Si eres tú, ingresa el mismo correo que usaste."},status=status.HTTP_409_CONFLICT)
            return Response(AsistenteSerializer(existing).data|{"recuperado":True})
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
    def get(self,request):
        qs=RetiroCompleto.objects.select_related("asistente","validado_por").all()[:200]
        return Response(RetiroSerializer(qs,many=True).data)
    def post(self,request):
        attendee=get_object_or_404(Asistente,codigo=str(request.data.get("codigo","")).upper())
        try: cantidad=int(request.data.get("cantidad"))
        except (TypeError,ValueError):
            return Response({"detail":"La cantidad debe ser 1 o 2."},status=status.HTTP_400_BAD_REQUEST)
        try: retiro=registrar_retiro(attendee,cantidad,request.user)
        except DjangoValidationError as exc:
            return Response({"detail":exc.messages[0]},status=status.HTTP_400_BAD_REQUEST)
        return Response(RetiroSerializer(retiro).data,status=201)
class AdminResumenView(APIView):
    permission_classes=[IsAuthenticated]
    def get(self,request):
        from torneos.models import Torneo
        areas=Area.objects.annotate(total=Count("asistente")).filter(total__gt=0).order_by("-total","orden","nombre")
        carreras=Carrera.objects.annotate(total=Count("asistente")).filter(total__gt=0).select_related("area").order_by("-total","nombre")
        return Response({"total_registrados":Asistente.objects.count(),"completos_entregados":RetiroCompleto.objects.aggregate(v=Sum("cantidad"))["v"] or 0,"completos_pendientes":Asistente.objects.aggregate(v=Sum(F("completos_asignados")-F("completos_retirados")))["v"] or 0,"inscritos_por_torneo":[{"slug":t.slug,"nombre":t.nombre,"inscritos":t.equipos.filter(estado="confirmado").count()} for t in Torneo.objects.all()],"aportes_comprometidos":{x["aporte"]:x["total"] for x in Asistente.objects.values("aporte").annotate(total=Count("id"))},"asistentes_por_area":[{"slug":x.slug,"nombre":x.nombre,"total":x.total} for x in areas],"asistentes_por_carrera":[{"slug":x.slug,"nombre":x.nombre,"area":x.area.slug,"total":x.total} for x in carreras]})
