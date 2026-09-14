from django.urls import path
from .views import *
urlpatterns=[path("catalogo/areas/",CatalogoAreasView.as_view()),path("asistentes/",RegistroView.as_view()),path("pase/<str:codigo>/",PaseView.as_view()),path("admin/asistentes/",AdminAsistentesView.as_view()),path("admin/asistentes/<str:codigo>/",AdminAsistenteView.as_view()),path("admin/retiros/",AdminRetirosView.as_view()),path("admin/resumen/",AdminResumenView.as_view())]
