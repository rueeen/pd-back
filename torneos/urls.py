from django.urls import path
from .views import *
urlpatterns=[path("torneos/",TorneosView.as_view()),path("torneos/<slug:slug>/",TorneoView.as_view()),path("torneos/<slug:slug>/inscripcion/",InscripcionView.as_view()),path("torneos/<slug:slug>/bracket/",BracketView.as_view()),path("admin/torneos/<slug:slug>/sorteo/",SorteoView.as_view()),path("admin/partidas/<int:pk>/resultado/",ResultadoView.as_view()),path("admin/equipos/<int:pk>/",EquipoAdminView.as_view())]
