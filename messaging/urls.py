from django.urls import path

from . import views

urlpatterns = [
    path("", views.inbox, name="inbox"),
    path("to/<int:pk>/", views.send, name="send_message"),
    path("notifications/<int:pk>/", views.open_notification, name="open_notification"),
    path("notifications/read-all/", views.read_all_notifications, name="read_all_notifications"),
]
