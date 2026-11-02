from datetime import timedelta
from .models import Activity, Attendance, DailyRecord

from django.db.models import Q
from accounts.models import User
from .models import Child, Classroom

import logging
import re
import secrets
from datetime import datetime, timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.utils.html import escape
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.hashers import check_password, make_password
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.views import admin_required, staff_required
from messaging.models import notify




from .forms import ActivityForm, ChildForm, ClassroomForm, MealForm, NapForm

from .models import Activity, Attendance, Child, Classroom, DailyRecord, MediaItem, PickupCode, PickupRecord

log = logging.getLogger("littlenest.pickup")


# ---------- helpers ----------

def now_time():
    return timezone.localtime().time().replace(second=0, microsecond=0)


def today():
    return timezone.localdate()


def parse_day(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return today()


def greeting():
    h = timezone.localtime().hour
    return "Good morning" if h < 12 else "Good afternoon" if h < 17 else "Good evening"


def day_status(att, rec):
    if att and att.check_out:
        return "out"
    if att and att.check_in:
        return "napping" if rec and rec.is_napping else "in"
    return "expected"


def record_for(child, day, create=False):
    if create:
        return DailyRecord.objects.get_or_create(child=child, date=day)[0]
    return DailyRecord.objects.filter(child=child, date=day).prefetch_related("meals").first()


def managed_child(request, pk):
    child = get_object_or_404(Child.objects.select_related("classroom", "parent"), pk=pk)
    if not can_manage_child(request.user, child):
        raise PermissionDenied
    return child


def back_to(request, fallback):
    nxt = request.POST.get("next") or request.GET.get("next")
    return redirect(nxt if nxt and nxt.startswith("/") else fallback)


def not_found(request, exception=None):
    return render(request, "404.html", status=404)


# ---------- dashboard ----------

@login_required
def dashboard(request):
    if request.user.is_parent:
        return parent_dashboard(request)
    me, day = request.user, today()
    classes = list(visible_classes(me))
    default_room = "" if me.is_admin_role or not classes else str(classes[0].pk)
    room = request.GET.get("room", default_room)
    scope_classes = [c for c in classes if str(c.pk) == room]
    if not scope_classes:
        room, scope_classes = "", classes
    class_ids = [c.pk for c in scope_classes]
    children = list(visible_children(me).filter(classroom_id__in=class_ids).order_by("first_name"))
    child_ids = [c.pk for c in children]

    att = {a.child_id: a for a in Attendance.objects.filter(date=day, child_id__in=child_ids)}
    recs = {r.child_id: r for r in DailyRecord.objects.filter(date=day, child_id__in=child_ids)}
    q = request.GET.get("q", "").strip().lower()
    status = request.GET.get("status", "")
    rows = []
    for c in children:
        st = day_status(att.get(c.pk), recs.get(c.pk))
        if (q and q not in c.full_name.lower()) or (status and st != status):
            continue
        rows.append({"child": c, "att": att.get(c.pk), "rec": recs.get(c.pk), "status": st, "present": st in ("in", "napping")})

    insight = build_insight(child_ids, class_ids, day)
    single = scope_classes[0] if len(scope_classes) == 1 else None
    return render(request, "nursery/dashboard.html", {
        "greeting": greeting(), "classes": classes, "room": room, "single": single,
        "scope_label": f"{single.name} Room ({single.age_group})" if single else "All rooms",
        "rows": rows, "total": len(children), "insight": insight, "s": insight["summary"],
        "activities": Activity.objects.filter(date=day, classroom_id__in=class_ids).select_related("classroom")[:3],
        "multi_room": len(scope_classes) > 1, "q": q, "status": status, "today": day,
        "statuses": [("", "All status"), ("in", "Checked in"), ("napping", "Napping"), ("expected", "Expected"), ("out", "Picked up")],
    })


def parent_dashboard(request):
    day = today()
    monday = day - timedelta(days=day.weekday())
    week = [monday + timedelta(days=i) for i in range(5)]
    cards = []
    for child in visible_children(request.user):
        att = Attendance.objects.filter(child=child, date=day).first()
        rec = record_for(child, day)
        present_days = set(Attendance.objects.filter(child=child, date__in=week, check_in__isnull=False).values_list("date", flat=True))
        cards.append({
            "child": child, "att": att, "rec": rec, "status": day_status(att, rec),
            "media": MediaItem.objects.filter(child=child, date=day)[:4],
            "week": [{"day": d, "present": d in present_days, "future": d > day, "today": d == day} for d in week],
            "activities": Activity.objects.filter(classroom=child.classroom, date=day)[:3] if child.classroom else [],
        })
    return render(request, "nursery/parent_dashboard.html", {"cards": cards, "greeting": greeting(), "today": day})


# ---------- children ----------

SORTS = {"name": ("first_name", "last_name"), "-name": ("-first_name", "-last_name"), "age": ("-birth_date",), "-age": ("birth_date",), "class": ("classroom__name", "first_name")}


@login_required
def children_list(request):
    qs = visible_children(request.user)
    q = request.GET.get("q", "").strip()
    room = request.GET.get("room", "")
    sort = request.GET.get("sort", "name")
    if q:
        qs = qs.filter(Q(first_name__icontains=q) | Q(last_name__icontains=q) | Q(parent__name__icontains=q))
    if room == "none":
        qs = qs.filter(classroom__isnull=True)
    elif room:
        qs = qs.filter(classroom_id=room)
    qs = qs.order_by(*SORTS.get(sort, SORTS["name"]))
    page = Paginator(qs, 10).get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)
    return render(request, "nursery/children.html", {
        "page": page, "q": q, "room": room, "sort": sort, "classes": visible_classes(request.user),
        "qs": params.urlencode(),
    })


@admin_required
def child_create(request):
    form = ChildForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        child = form.save()
        messages.success(request, f"{child.first_name} added")
        return redirect("child_detail", pk=child.pk)
    return render(request, "nursery/child_form.html", {"form": form})


@login_required
def child_edit(request, pk):
    child = get_object_or_404(Child, pk=pk)
    if not (request.user.is_admin_role or can_manage_child(request.user, child)):
        raise PermissionDenied
    form = ChildForm(request.POST or None, request.FILES or None, instance=child)
    if not request.user.is_admin_role:
        form.fields.pop("classroom")
        form.fields.pop("parent")
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Profile updated")
        return redirect("child_detail", pk=child.pk)
    return render(request, "nursery/child_form.html", {"form": form, "child": child})


@admin_required
@require_POST
def child_delete(request, pk):
    child = get_object_or_404(Child, pk=pk)
    name = child.full_name
    child.delete()
    messages.success(request, f"{name} removed")
    return redirect("children")


@login_required
def child_detail(request, pk):
    child = get_object_or_404(Child.objects.select_related("classroom__teacher", "parent"), pk=pk)
    if not can_view_child(request.user, child):
        raise PermissionDenied
    day = parse_day(request.GET.get("date"))
    rec = record_for(child, day)
    att = Attendance.objects.filter(child=child, date=day).first()
    history = []
    for a in Attendance.objects.filter(child=child)[:20]:
        mins = 0
        if a.check_in and a.check_out:
            mins = (a.check_out.hour * 60 + a.check_out.minute) - (a.check_in.hour * 60 + a.check_in.minute)
        history.append({"a": a, "hours": f"{mins // 60}h {mins % 60:02d}m" if mins else "—"})
    return render(request, "nursery/child_detail.html", {
        "child": child, "day": day, "is_today": day == today(), "rec": rec, "att": att,
        "status": day_status(att, rec), "media": MediaItem.objects.filter(child=child, date=day),
        "prev": day - timedelta(days=1), "next": day + timedelta(days=1) if day < today() else None,
        "tab": request.GET.get("tab", "day"), "history": history,
        "can_manage": can_manage_child(request.user, child),
        "meal_form": MealForm(initial={"time": now_time().strftime("%H:%M"), "meal": "lunch", "amount": "all"}),
        "nap_form": NapForm(initial={"nap_start": rec.nap_start if rec else None, "nap_end": rec.nap_end if rec else None, "nap_note": rec.nap_note if rec else ""}),
        "moods": DailyRecord.MOODS, "pickups": PickupRecord.objects.filter(child=child)[:5],
    })


# ---------- attendance & pickup ----------

# Attendance and pickup views are in the attendance app.


@staff_required
@require_POST
def meal_add(request, pk):
    child = managed_child(request, pk)
    day = parse_day(request.POST.get("date"))
    form = MealForm(request.POST)
    if form.is_valid():
        rec = record_for(child, day, create=True)
        meal = form.save(commit=False)
        meal.record = rec
        meal.save()
        rec.last_activity = meal.get_meal_display()
        rec.save(update_fields=["last_activity"])
        messages.success(request, f"{meal.get_meal_display()} logged for {child.first_name}")
    else:
        messages.error(request, "Please fill in the food and time.")
    return redirect(f"{reverse('child_detail', args=[child.pk])}?date={day:%Y-%m-%d}")


@staff_required
@require_POST
def meal_delete(request, pk, meal_id):
    child = managed_child(request, pk)
    rec = get_object_or_404(DailyRecord, child=child, meals__id=meal_id)
    rec.meals.filter(pk=meal_id).delete()
    return redirect(f"{reverse('child_detail', args=[child.pk])}?date={rec.date:%Y-%m-%d}")


@staff_required
@require_POST
def nap_set(request, pk):
    child = managed_child(request, pk)
    day = parse_day(request.POST.get("date"))
    form = NapForm(request.POST)
    if form.is_valid():
        rec = record_for(child, day, create=True)
        rec.nap_start, rec.nap_end, rec.nap_note = form.cleaned_data["nap_start"], form.cleaned_data["nap_end"], form.cleaned_data["nap_note"]
        rec.last_activity = "Nap"
        rec.save()
        messages.success(request, "Nap saved")
    else:
        messages.error(request, " ".join(form.non_field_errors()) or "Check the nap times.")
    return redirect(f"{reverse('child_detail', args=[child.pk])}?date={day:%Y-%m-%d}")


@staff_required
@require_POST
def nap_now(request, pk):
    """Quick start/end nap from the dashboard row menu."""
    child = managed_child(request, pk)
    rec = record_for(child, today(), create=True)
    if rec.is_napping:
        rec.nap_end = now_time()
        msg = f"{child.first_name} woke up"
    else:
        rec.nap_start, rec.nap_end = now_time(), None
        msg = f"{child.first_name} is napping"
    rec.last_activity = "Nap"
    rec.save()
    messages.success(request, msg)
    return back_to(request, "dashboard")


@staff_required
@require_POST
def mood_set(request, pk):
    child = managed_child(request, pk)
    day = parse_day(request.POST.get("date"))
    mood = request.POST.get("mood", "")
    if mood in dict(DailyRecord.MOODS) or mood == "":
        rec = record_for(child, day, create=True)
        rec.mood, rec.mood_note = mood, request.POST.get("mood_note", "")[:200]
        rec.save(update_fields=["mood", "mood_note"])
        messages.success(request, "Mood saved")
    return back_to(request, f"{reverse('child_detail', args=[child.pk])}?date={day:%Y-%m-%d}")


@staff_required
@require_POST
def notes_save(request, pk):
    child = managed_child(request, pk)
    day = parse_day(request.POST.get("date"))
    rec = record_for(child, day, create=True)
    rec.notes = request.POST.get("notes", "").strip()
    rec.notes_updated_at, rec.notes_by = timezone.now(), request.user
    rec.save()
    if rec.notes:
        notify(child.parent, f"New note about {child.first_name}", reverse("child_detail", args=[child.pk]))
    messages.success(request, "Notes saved")
    return redirect(f"{reverse('child_detail', args=[child.pk])}?date={day:%Y-%m-%d}")


# ---------- media ----------

@staff_required
@require_POST
def media_upload(request, pk):
    child = managed_child(request, pk)
    day = parse_day(request.POST.get("date"))
    files = request.FILES.getlist("files")
    added = 0
    for f in files[:10]:
        ctype = (f.content_type or "").lower()
        if ctype.startswith("image/"):
            kind = "image"
        elif ctype.startswith("video/") and f.size <= settings.MAX_VIDEO_BYTES:
            kind = "video"
        else:
            messages.error(request, f"Skipped {f.name}: only photos and videos under 20 MB.")
            continue
        MediaItem.objects.create(child=child, file=f, kind=kind, date=day, caption=request.POST.get("caption", "")[:160], uploaded_by=request.user)
        added += 1
    if added:
        notify(child.parent, f"{added} new {'photo' if added == 1 else 'photos'} of {child.first_name}", reverse("child_detail", args=[child.pk]))
        messages.success(request, f"{added} uploaded")
    return redirect(f"{reverse('child_detail', args=[child.pk])}?date={day:%Y-%m-%d}")


@staff_required
@require_POST
def media_update(request, pk, media_id):
    child = managed_child(request, pk)
    item = get_object_or_404(MediaItem, pk=media_id, child=child)
    if request.POST.get("action") == "delete":
        item.file.delete(save=False)
        item.delete()
        messages.success(request, "Deleted")
    else:
        item.caption = request.POST.get("caption", "")[:160]
        item.save(update_fields=["caption"])
        messages.success(request, "Caption saved")
    return redirect(f"{reverse('child_detail', args=[child.pk])}?date={item.date:%Y-%m-%d}")


# ---------- classes ----------

@staff_required
def classes_list(request):
    classes = visible_classes(request.user).select_related("teacher").annotate(n=Count("children"))
    form = ClassroomForm(request.POST or None)
    if request.method == "POST":
        if not request.user.is_admin_role:
            raise PermissionDenied
        if form.is_valid():
            c = form.save()
            messages.success(request, f"{c.name} created")
            return redirect("class_detail", pk=c.pk)
    day = today()
    cards = []
    for c in classes:
        present = Attendance.objects.filter(child__classroom=c, date=day, check_in__isnull=False, check_out__isnull=True).count()
        cards.append({"c": c, "present": present, "fill": min(100, round(c.n / c.capacity * 100)) if c.capacity else 0,
                      "next": Activity.objects.filter(classroom=c, date=day, time__gte=now_time()).first()})
    return render(request, "nursery/classes.html", {"cards": cards, "form": form, "open_dialog": request.method == "POST"})


@staff_required
def class_detail(request, pk):
    c = get_object_or_404(visible_classes(request.user).select_related("teacher"), pk=pk)
    is_admin = request.user.is_admin_role
    can_plan = is_admin or c.teacher_id == request.user.id
    day = parse_day(request.GET.get("date"))
    edit_form = ClassroomForm(instance=c)
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "edit" and is_admin:
            edit_form = ClassroomForm(request.POST, instance=c)
            if edit_form.is_valid():
                edit_form.save()
                messages.success(request, "Class updated")
                return redirect("class_detail", pk=c.pk)
        elif action == "delete" and is_admin:
            c.delete()
            messages.success(request, "Class deleted")
            return redirect("classes")
        elif action == "enroll" and is_admin:
            Child.objects.filter(pk=request.POST.get("child")).update(classroom=c)
            messages.success(request, "Child enrolled")
            return redirect("class_detail", pk=c.pk)
        elif action == "unenroll" and is_admin:
            Child.objects.filter(pk=request.POST.get("child"), classroom=c).update(classroom=None)
            messages.success(request, "Removed from class")
            return redirect("class_detail", pk=c.pk)
        elif action == "add_activity" and can_plan:
            f = ActivityForm(request.POST)
            if f.is_valid():
                a = f.save(commit=False)
                a.classroom, a.date = c, day
                a.save()
                messages.success(request, "Activity added")
            else:
                messages.error(request, "Add a time and title.")
            return redirect(f"{reverse('class_detail', args=[c.pk])}?date={day:%Y-%m-%d}")
        elif action == "delete_activity" and can_plan:
            Activity.objects.filter(pk=request.POST.get("activity"), classroom=c).delete()
            return redirect(f"{reverse('class_detail', args=[c.pk])}?date={day:%Y-%m-%d}")
        else:
            raise PermissionDenied

    roster = list(c.children.select_related("parent"))
    att = {a.child_id: a for a in Attendance.objects.filter(date=today(), child__in=roster)}
    recs = {r.child_id: r for r in DailyRecord.objects.filter(date=today(), child__in=roster)}
    return render(request, "nursery/class_detail.html", {
        "c": c, "is_admin": is_admin, "can_plan": can_plan, "day": day, "edit_form": edit_form,
        "roster": [{"child": ch, "status": day_status(att.get(ch.pk), recs.get(ch.pk)), "att": att.get(ch.pk)} for ch in roster],
        "activities": Activity.objects.filter(classroom=c, date=day),
        "candidates": Child.objects.exclude(classroom=c).order_by("first_name") if is_admin else [],
        "activity_form": ActivityForm(), "prev": day - timedelta(days=1), "next": day + timedelta(days=1),
        "fill": min(100, round(len(roster) / c.capacity * 100)) if c.capacity else 0,
    })


# ---------- reports ----------

# Reporting views are in the reports app.


# ---- access helpers ----

def visible_classes(user):
    if user.is_admin_role:
        return Classroom.objects.all()
    if user.is_teacher:
        return Classroom.objects.filter(teacher=user)
    return Classroom.objects.filter(children__parent=user).distinct()

def visible_children(user):
    qs = Child.objects.select_related("classroom", "parent")
    if user.is_admin_role:
        return qs
    if user.is_teacher:
        return qs.filter(classroom__teacher=user)
    return qs.filter(parent=user)

def can_view_child(user, child):
    return visible_children(user).filter(pk=child.pk).exists()

def can_manage_child(user, child):
    """Staff who may log records, check in/out and upload media."""
    if user.is_admin_role:
        return True
    return user.is_teacher and child.classroom_id is not None and child.classroom.teacher_id == user.id

def message_contacts(user):
    """Parents talk to their children's teachers and admins; staff talk to their families and each other."""
    if user.is_parent:
        return User.objects.filter(
            Q(role="admin") | Q(classrooms__children__parent=user)
        ).exclude(pk=user.pk).distinct()
    if user.is_teacher:
        return User.objects.filter(
            Q(role__in=["admin", "teacher"]) | Q(children__classroom__teacher=user)
        ).exclude(pk=user.pk).distinct()
    return User.objects.exclude(pk=user.pk)


# ---- insight helpers ----

def previous_weekdays(day, count):
    out, d = [], day
    while len(out) < count:
        d -= timedelta(days=1)
        if d.weekday() < 5:
            out.append(d)
    return out

def duration_label(mins):
    h, m = divmod(mins, 60)
    if h and m:
        return f"{h}h {m}m"
    return f"{h}h" if h else f"{m}m"

def summarize_day(child_ids, class_ids, day):
    child_ids = list(child_ids)
    att = Attendance.objects.filter(date=day, child_id__in=child_ids, check_in__isnull=False)
    recs = list(DailyRecord.objects.filter(date=day, child_id__in=child_ids).prefetch_related("meals"))
    naps = [r for r in recs if r.nap_start and r.nap_end]
    total = sum(r.nap_minutes for r in naps)
    return {
        "expected": len(child_ids),
        "present": att.count(),
        "checked_out": att.filter(check_out__isnull=False).count(),
        "meals_logged": sum(len(r.meals.all()) for r in recs),
        "low_lunch": sum(1 for r in recs if any(m.meal == "lunch" and m.amount in ("some", "none") for m in r.meals.all())),
        "napping": sum(1 for r in recs if r.is_napping),
        "napped": len(naps),
        "avg_nap": round(total / len(naps)) if naps else 0,
        "activities": Activity.objects.filter(date=day, classroom_id__in=list(class_ids)).count(),
        "upset": sum(1 for r in recs if r.mood in ("upset", "fussy")),
    }

def _rate(child_ids, day):
    if not child_ids or not Attendance.objects.filter(date=day).exists():
        return None
    present = Attendance.objects.filter(date=day, child_id__in=child_ids, check_in__isnull=False).count()
    return present / len(child_ids)

def build_insight(child_ids, class_ids, day):
    child_ids = list(child_ids)
    s = summarize_day(child_ids, class_ids, day)
    rate = s["present"] / s["expected"] if s["expected"] else 0
    prior = [r for r in (_rate(child_ids, d) for d in previous_weekdays(day, 5)) if r is not None]
    last_week = sum(prior) / len(prior) if prior else None
    pct = lambda v: f"{round(v * 100)}%"  # noqa: E731

    sentences = []
    if s["expected"] == 0:
        sentences.append("No children are enrolled here yet.")
    elif last_week is not None:
        direction = "above" if rate > last_week + 0.02 else "below" if rate < last_week - 0.02 else "in line with"
        sentences.append(f"Attendance is {pct(rate)}, {direction} last week's {pct(last_week)}.")
    else:
        sentences.append(f"Attendance is {pct(rate)} ({s['present']} of {s['expected']}).")
    if s["low_lunch"]:
        sentences.append(f"{s['low_lunch']} {'child' if s['low_lunch'] == 1 else 'children'} ate little at lunch.")
    elif s["meals_logged"]:
        sentences.append("Everyone with a logged lunch ate well.")
    if s["napping"]:
        sentences.append(f"{s['napping']} {'is' if s['napping'] == 1 else 'are'} napping right now.")
    elif s["napped"]:
        sentences.append(f"{s['napped']} napped, averaging {duration_label(s['avg_nap'])}.")
    if s["activities"]:
        sentences.append(f"{s['activities']} {'activity' if s['activities'] == 1 else 'activities'} planned today.")

    if s["expected"] and rate < 0.6:
        tip = ("Low turnout today", "Consider a quick check-in message to families who haven't arrived.", "watch")
    elif s["low_lunch"] >= 3:
        tip = ("Watch lunch intake", "Offer an extra afternoon snack and note it for parents.", "watch")
    elif s["upset"] >= 2:
        tip = ("A few tough moods", "A calm-down corner or quiet story could help this afternoon.", "watch")
    elif last_week is not None and rate >= last_week:
        tip = ("Keep it up!", "Attendance is trending in the right direction this week.", "good")
    else:
        tip = ("Steady day", "Everything is on track. Remember to log naps and meals as they happen.", "neutral")
    return {
        "text": " ".join(sentences),
        "tip": {"title": tip[0], "body": tip[1], "tone": tip[2]},
        "rate": rate,
        "last_week": last_week,
        "summary": s,
    }
