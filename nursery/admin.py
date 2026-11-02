from django.contrib import admin

from .models import Activity, Attendance, Child, Classroom, DailyRecord, Meal, MediaItem, PickupRecord


class MealInline(admin.TabularInline):
    model = Meal
    extra = 0


@admin.register(Classroom)
class ClassroomAdmin(admin.ModelAdmin):
    list_display = ["name", "age_group", "capacity", "teacher"]


@admin.register(Child)
class ChildAdmin(admin.ModelAdmin):
    list_display = ["full_name", "classroom", "parent", "allergies"]
    list_filter = ["classroom"]
    search_fields = ["first_name", "last_name"]


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ["child", "date", "check_in", "check_out", "picked_up_by"]
    list_filter = ["date"]


@admin.register(DailyRecord)
class DailyRecordAdmin(admin.ModelAdmin):
    list_display = ["child", "date", "mood", "nap_start", "nap_end"]
    list_filter = ["date"]
    inlines = [MealInline]


admin.site.register(Activity)
admin.site.register(MediaItem)
admin.site.register(PickupRecord)
