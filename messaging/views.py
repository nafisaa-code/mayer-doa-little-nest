

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from accounts.models import User
from nursery.views import message_contacts

from .models import Message, Notification, notify


@login_required
def inbox(request):
    me = request.user
    contacts = list(message_contacts(me))
    extra_ids = Message.objects.filter(recipient=me).values_list("sender_id", flat=True)
    for u in User.objects.filter(pk__in=extra_ids).exclude(pk__in=[c.pk for c in contacts]):
        contacts.append(u)

    threads = []
    for c in contacts:
        last = Message.objects.filter(Q(sender=me, recipient=c) | Q(sender=c, recipient=me)).order_by("-sent_at").first()
        unread = Message.objects.filter(sender=c, recipient=me, read=False).count()
        threads.append({"user": c, "last": last, "unread": unread})
    threads.sort(key=lambda t: (t["last"] is None, -(t["last"].sent_at.timestamp() if t["last"] else 0), t["user"].name))

    q = request.GET.get("q", "").strip().lower()
    if q:
        threads = [t for t in threads if q in t["user"].name.lower()]

    active = None
    convo = []
    with_id = request.GET.get("with")
    if with_id:
        active = next((t["user"] for t in threads if str(t["user"].pk) == with_id), None)
    if active:
        Message.objects.filter(sender=active, recipient=me, read=False).update(read=True)
        convo = Message.objects.filter(Q(sender=me, recipient=active) | Q(sender=active, recipient=me)).select_related("sender")
        for t in threads:
            if t["user"] == active:
                t["unread"] = 0
    return render(request, "messaging/inbox.html", {"threads": threads, "active": active, "convo": convo, "q": q})


@login_required
@require_POST
def send(request, pk):
    other = get_object_or_404(User, pk=pk)
    body = request.POST.get("body", "").strip()
    allowed = message_contacts(request.user).filter(pk=other.pk).exists() or Message.objects.filter(sender=other, recipient=request.user).exists()
    if body and allowed:
        Message.objects.create(sender=request.user, recipient=other, body=body[:2000])
        notify(other, f"New message from {request.user.name}", f"{reverse('inbox')}?with={request.user.pk}")
    return redirect(f"{reverse('inbox')}?with={other.pk}")


@login_required
def open_notification(request, pk):
    n = get_object_or_404(Notification, pk=pk, user=request.user)
    n.read = True
    n.save(update_fields=["read"])
    if n.link and url_has_allowed_host_and_scheme(n.link, allowed_hosts={request.get_host()}):
        return redirect(n.link)
    return redirect("dashboard")


@login_required
@require_POST
def read_all_notifications(request):
    request.user.notifications.filter(read=False).update(read=True)
    nxt = request.POST.get("next", "")
    return redirect(nxt if url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}) else "dashboard")

def inbox_context(request):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {}
    notes = user.notifications.all()[:8]
    return {
        "unread_messages": user.received_messages.filter(read=False).count(),
        "unread_notifications": user.notifications.filter(read=False).count(),
        "recent_notifications": notes,
    }


