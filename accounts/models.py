from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, password=None, **extra):
        if not email:
            raise ValueError("Email is required")
        user = self.model(email=self.normalize_email(email).lower(), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        extra.setdefault("role", User.Role.ADMIN)
        return self.create_user(email, password, **extra)


class User(AbstractUser):
    """A Little Nest account. Logs in with email; role drives every permission."""

    class Role(models.TextChoices):
        PARENT = "parent", "Parent"
        TEACHER = "teacher", "Teacher"
        ADMIN = "admin", "Admin"

    username = None
    first_name = None
    last_name = None
    name = models.CharField(max_length=120)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=30, blank=True)
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.PARENT)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["name"]
    objects = UserManager()

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def first(self):
        return self.name.split(" ")[0]

    @property
    def initials(self):
        return "".join(p[0].upper() for p in self.name.split()[:2] if p)

    @property
    def is_parent(self):
        return self.role == self.Role.PARENT

    @property
    def is_teacher(self):
        return self.role == self.Role.TEACHER

    @property
    def is_admin_role(self):
        return self.role == self.Role.ADMIN

    @property
    def is_staff_member(self):
        return self.role in (self.Role.TEACHER, self.Role.ADMIN)
