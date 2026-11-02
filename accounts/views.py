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
