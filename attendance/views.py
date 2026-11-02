"""Child check-in and secure pickup.

Models remain in nursery to preserve the existing database and migrations.
"""
import logging
import re
import secrets
from datetime import timedelta
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.hashers import make_password, check_password
from django.core.mail import send_mail
from django.db import transaction
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.html import escape
from django.views.decorators.http import require_POST
from accounts.views import staff_required
from messaging.models import notify
from nursery.models import Attendance, PickupCode, PickupRecord
from nursery.views import managed_child, now_time, today, back_to

@staff_required
@require_POST
def check_in(request, pk):
    child = managed_child(request, pk)
    t = now_time()
    Attendance.objects.update_or_create(child=child, date=today(), defaults={"check_in": t, "check_out": None, "picked_up_by": ""})
    notify(child.parent, f"{child.first_name} checked in at {t:%H:%M}", reverse("child_detail", args=[child.pk]))
    messages.success(request, f"{child.first_name} checked in · parent notified")
    return back_to(request, "dashboard")


# ---- email helpers ----

def mask_email(email):
    if not email or "@" not in email:
        return "no email on file"
    name, domain = email.split("@", 1)
    return f"{name[:1]}{'•' * max(2, min(len(name) - 1, 5))}@{domain}"

def send_pickup_code_email(parent, child_name, code):
    """Raises on SMTP failure so the caller can show a clear error."""
    text = (
        f"Hi {parent.name},\n\nYour মায়ের দোয়া Little Nest pickup code for {child_name} is {code}.\n"
        "Share it with the teacher at checkout. It is valid for 5 minutes.\n\n"
        f"If you are not picking up {child_name} right now, please call the nursery.\n\nমায়ের দোয়া Little Nest"
    )
    n, c = escape(parent.name), escape(child_name)
    html = f"""<div style="background:#F3F7F8;padding:32px 16px;font-family:Arial,Helvetica,sans-serif;color:#14262B">
<div style="max-width:480px;margin:0 auto;background:#fff;border:1px solid #DCE6E9;border-radius:12px;padding:28px">
<div style="font-size:18px;font-weight:800;color:#1F5E6B">মায়ের দোয়া Little Nest</div>
<p style="font-size:15px;line-height:22px;color:#5F7479">Hi {n}, here is your pickup code for <strong style="color:#14262B">{c}</strong>.</p>
<div style="text-align:center;margin:24px 0"><span style="display:inline-block;padding:14px 22px;border-radius:12px;background:#F3F7F8;border:1px solid #DCE6E9;font-size:34px;letter-spacing:10px;font-weight:800;color:#2F7D8C">{code}</span></div>
<p style="font-size:14px;line-height:21px;color:#5F7479">Share it with the teacher at checkout. It is valid for 5 minutes. If you are not picking up {c} right now, please call the nursery.</p>
</div></div>"""
    send_mail(f"Pickup code for {child_name}", text, None, [parent.email], html_message=html)

