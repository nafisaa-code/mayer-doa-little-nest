from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("children/", views.children_list, name="children"),
    path("children/new/", views.child_create, name="child_create"),
    path("children/<int:pk>/", views.child_detail, name="child_detail"),
    path("children/<int:pk>/edit/", views.child_edit, name="child_edit"),
    path("children/<int:pk>/delete/", views.child_delete, name="child_delete"),
    path("children/<int:pk>/meals/", views.meal_add, name="meal_add"),
    path("children/<int:pk>/meals/<int:meal_id>/delete/", views.meal_delete, name="meal_delete"),
    path("children/<int:pk>/nap/", views.nap_set, name="nap_set"),
    path("children/<int:pk>/nap/now/", views.nap_now, name="nap_now"),
    path("children/<int:pk>/mood/", views.mood_set, name="mood_set"),
    path("children/<int:pk>/notes/", views.notes_save, name="notes_save"),
    path("children/<int:pk>/media/", views.media_upload, name="media_upload"),
    path("children/<int:pk>/media/<int:media_id>/", views.media_update, name="media_update"),
    path("classes/", views.classes_list, name="classes"),
    path("classes/<int:pk>/", views.class_detail, name="class_detail"),
]
