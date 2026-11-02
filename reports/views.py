"""Daycare reports, using data from existing nursery models."""
from datetime import timedelta
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from nursery.models import Attendance, DailyRecord
from nursery.views import (parse_day, visible_classes, visible_children,
    build_insight, previous_weekdays, day_status, today)

@login_required
def reports(request):
    me = request.user
    day = parse_day(request.GET.get("date"))
    classes = list(visible_classes(me))
    room = request.GET.get("room", "")
    scope = [c for c in classes if str(c.pk) == room] or classes
    children = visible_children(me)
    if not me.is_parent:
        children = children.filter(classroom__in=scope)
    children = list(children.order_by("first_name"))
    ids = [c.pk for c in children]
    insight = build_insight(ids, [c.pk for c in scope], day)

    week_days = list(reversed(previous_weekdays(day + timedelta(days=1), 5)))
    bars = []
    for d in week_days:
        present = Attendance.objects.filter(date=d, child_id__in=ids, check_in__isnull=False).count()
        bars.append({"day": d, "present": present, "pct": round(present / len(ids) * 100) if ids else 0, "current": d == day})

    att = {a.child_id: a for a in Attendance.objects.filter(date=day, child_id__in=ids)}
    recs = {r.child_id: r for r in DailyRecord.objects.filter(date=day, child_id__in=ids).prefetch_related("meals")}
    rows = [{"child": c, "att": att.get(c.pk), "rec": recs.get(c.pk), "status": day_status(att.get(c.pk), recs.get(c.pk))} for c in children]
    return render(request, "nursery/reports.html", {
        "day": day, "classes": classes, "room": room, "insight": insight, "s": insight["summary"],
        "bars": bars, "rows": rows, "prev": day - timedelta(days=1), "next": day + timedelta(days=1) if day < today() else None,
    })



