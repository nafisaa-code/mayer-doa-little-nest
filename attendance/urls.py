from django.urls import path
from . import views

urlpatterns = [
    path("children/<int:pk>/check-in/", views.check_in, name="check_in"),
    path("children/<int:pk>/pickup/", views.pickup, name="pickup"),
]
