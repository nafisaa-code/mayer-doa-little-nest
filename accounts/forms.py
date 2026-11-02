from django import forms
from django.contrib.auth import authenticate, password_validation

from .models import User


class LoginForm(forms.Form):
    email = forms.EmailField()
    password = forms.CharField(widget=forms.PasswordInput)

    def clean(self):
        data = super().clean()
        email, password = data.get("email"), data.get("password")
        if email and password:
            self.user = authenticate(email=email.lower(), password=password)
            if self.user is None:
                raise forms.ValidationError("That email and password don't match an account.")
        return data


class RegisterForm(forms.ModelForm):
    """Public sign-up always creates a Parent account."""

    password = forms.CharField(widget=forms.PasswordInput, min_length=8)

    class Meta:
        model = User
        fields = ["name", "email", "phone"]

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = User.Role.PARENT
        user.set_password(self.cleaned_data["password"])
        if commit:
            user.save()
        return user


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["name", "email", "phone"]

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Another account already uses this email.")
        return email


class PasswordChangeForm(forms.Form):
    current = forms.CharField(widget=forms.PasswordInput, label="Current password")
    new = forms.CharField(widget=forms.PasswordInput, label="New password")

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_current(self):
        if not self.user.check_password(self.cleaned_data["current"]):
            raise forms.ValidationError("Current password is incorrect.")
        return self.cleaned_data["current"]

    def clean_new(self):
        password_validation.validate_password(self.cleaned_data["new"], self.user)
        return self.cleaned_data["new"]


class UserCreateForm(forms.ModelForm):
    password = forms.CharField(label="Temporary password", min_length=8)

    class Meta:
        model = User
        fields = ["name", "email", "phone", "role"]

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password"])
        if commit:
            user.save()
        return user
