from functools import wraps
from django.core.exceptions import PermissionDenied

from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from nursery.models import Child, Classroom


from .forms import LoginForm, PasswordChangeForm, ProfileForm, RegisterForm, UserCreateForm
from .models import User


# ---- decorators helpers ----

def role_required(*roles):
    """Allow only signed-in users whose role is in `roles`."""

    def decorator(view):
        @login_required
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if request.user.role not in roles:
                raise PermissionDenied
            return view(request, *args, **kwargs)

        return wrapped

    return decorator

staff_required = role_required("teacher", "admin")

admin_required = role_required("admin")


DEMO_ACCOUNTS = [
    {"label": "Teacher", "name": "Nusrat Jahan", "initials": "NJ", "email": "nusrat@littlenest.app"},
    {"label": "Parent", "name": "Sadia Chowdhury", "initials": "SC", "email": "sadia@example.com"},
    {"label": "Admin", "name": "Farhana Rahman", "initials": "FR", "email": "admin@littlenest.app"},
]
DEMO_PASSWORD = "nest1234"


def login_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    form = LoginForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        login(request, form.user)
        return redirect(request.GET.get("next") or "dashboard")
    return render(request, "accounts/login.html", {"form": form, "demo": DEMO_ACCOUNTS, "demo_password": DEMO_PASSWORD})


def register_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    form = RegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        messages.success(request, f"Welcome to মায়ের দোয়া Little Nest, {user.first}!")
        return redirect("dashboard")
    return render(request, "accounts/register.html", {"form": form})


@require_POST
def logout_view(request):
    logout(request)
    return redirect("login")


@login_required
def profile_view(request):
    profile_form = ProfileForm(instance=request.user)
    password_form = PasswordChangeForm(request.user)
    if request.method == "POST":
        if request.POST.get("action") == "password":
            password_form = PasswordChangeForm(request.user, request.POST)
            if password_form.is_valid():
                request.user.set_password(password_form.cleaned_data["new"])
                request.user.save()
                update_session_auth_hash(request, request.user)
                messages.success(request, "Password updated")
                return redirect("profile")
        else:
            profile_form = ProfileForm(request.POST, instance=request.user)
            if profile_form.is_valid():
                profile_form.save()
                messages.success(request, "Profile saved")
                return redirect("profile")
    return render(request, "accounts/profile.html", {"profile_form": profile_form, "password_form": password_form})


@admin_required
def users_view(request):
    q = request.GET.get("q", "").strip()
    role = request.GET.get("role", "")
    users = User.objects.all().order_by("role", "name")
    if q:
        users = users.filter(Q(name__icontains=q) | Q(email__icontains=q))
    if role:
        users = users.filter(role=role)

    form = UserCreateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        messages.success(request, f"{user.name} added")
        return redirect("users")

    rows = []
    for u in users:
        if u.is_parent:
            linked = ", ".join(c.first_name for c in Child.objects.filter(parent=u))
        elif u.is_teacher:
            linked = ", ".join(c.name for c in Classroom.objects.filter(teacher=u))
        else:
            linked = "All"
        rows.append({"user": u, "linked": linked})
    return render(request, "accounts/users.html", {
        "rows": rows, "q": q, "role": role, "form": form, "roles": User.Role.choices,
        "open_dialog": request.method == "POST",
    })
