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




# ---- sms helpers ----

log = logging.getLogger("littlenest.sms")

def mask_phone(phone):
    digits = re.sub(r"\D", "", phone or "")
    return f"+880 ••••-••{digits[-4:]}" if digits else "no number on file"

def send_sms(phone, body):
    """Returns True when the message was handed to the gateway."""
    if settings.SMS_BACKEND == "console":
        log.warning("[sms] to %s: %s", phone, body)
        print(f"[sms] to {phone}: {body}")
        return True
    return _send_real(phone, body)

def _send_real(phone, body):  # pragma: no cover - provider specific
    raise NotImplementedError("Configure a real SMS provider in nursery/views.py")


def _issue_code(request, child, channel):
    """Phone is a demo (code shown on screen in DEBUG); email really sends. Returns an error string or None."""
    code = f"{secrets.randbelow(900000) + 100000}"
    parent = child.parent
    if channel == "email":
        if not parent.email:
            return "The parent has no email on file."
        try:
            send_pickup_code_email(parent, child.first_name, code)
        except Exception:  # SMTP/network errors
            log.exception("Pickup email failed for child %s", child.pk)
            return "Could not send the email. Try again or use phone."
        messages.info(request, f"Code emailed to {mask_email(parent.email)}")
    else:
        send_sms(parent.phone, f"মায়ের দোয়া Little Nest: your pickup code for {child.first_name} is {code}. Valid 5 minutes.")
        if settings.DEBUG and settings.SMS_BACKEND == "console":
            messages.info(request, f"SMS to {mask_phone(parent.phone)} — demo code: {code}")
        else:
            messages.info(request, f"Code sent to {mask_phone(parent.phone)}")
    PickupCode.objects.update_or_create(child=child, defaults={
        "code_hash": make_password(code), "channel": channel, "phone": parent.phone, "attempts": 0,
        "sent_at": timezone.now(), "expires_at": timezone.now() + timedelta(seconds=settings.OTP_TTL_SECONDS),
    })
    return None


@staff_required
def pickup(request, pk):
    child = managed_child(request, pk)
    if not child.parent:
        messages.error(request, "This child has no parent on file to verify pickup.")
        return redirect("child_detail", pk=child.pk)
    otp = PickupCode.objects.filter(child=child).first()
    error = None
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "send":
            channel = "email" if request.POST.get("channel") == "email" else "phone"
            if otp and (timezone.now() - otp.sent_at).total_seconds() < settings.OTP_RESEND_SECONDS:
                error = "Please wait a few seconds before resending."
            else:
                error = _issue_code(request, child, channel)
                if not error:
                    return redirect("pickup", pk=child.pk)

        elif action == "verify":
            code = "".join(request.POST.getlist("d")) or request.POST.get("code", "")
            by = request.POST.get("picked_up_by", "").strip() or child.parent.name
            if not otp:
                error = "No active code. Send a new one."
            elif timezone.now() > otp.expires_at:
                error = "This code has expired. Resend a new code."
            elif otp.attempts >= settings.OTP_MAX_ATTEMPTS:
                error = "Too many attempts. Resend a new code."
            elif not check_password(code, otp.code_hash):
                otp.attempts += 1
                otp.save(update_fields=["attempts"])
                error = f"Incorrect code. {settings.OTP_MAX_ATTEMPTS - otp.attempts} attempts left."
            else:
                t = now_time()
                Attendance.objects.update_or_create(child=child, date=today(), defaults={"check_out": t, "picked_up_by": by})
                PickupRecord.objects.create(child=child, date=today(), time=t, picked_up_by=by, verified_by=request.user)
                otp.delete()
                notify(child.parent, f"{child.first_name} was picked up by {by} at {t:%H:%M}", reverse("child_detail", args=[child.pk]))
                messages.success(request, f"{child.first_name} checked out · pickup verified")
                return redirect("dashboard")
    resend_in = 0
    if otp:
        resend_in = max(0, settings.OTP_RESEND_SECONDS - int((timezone.now() - otp.sent_at).total_seconds()))
    return render(request, "nursery/pickup.html", {
        "child": child, "otp": otp, "error": error, "masked_phone": mask_phone(child.parent.phone) if child.parent.phone else "",
        "masked_email": mask_email(child.parent.email) if child.parent.email else "",
        "resend_in": resend_in, "digits": range(6),
        "choosing": not otp or request.GET.get("choose") == "1",
        "recent": PickupRecord.objects.filter(child__in=visible_children(request.user)).select_related("child", "verified_by")[:6],
    })



