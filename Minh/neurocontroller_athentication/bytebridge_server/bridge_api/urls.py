from django.urls import path
from . import views

urlpatterns = [

    path('reflect/', views.ReflectView.as_view(), name='reflect'),
]