from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager, Permission
from django.utils import timezone
from countries.models import Country
import random
import uuid

from django.contrib.auth.models import PermissionsMixin

class CustomUserManager(BaseUserManager):
    def create_user(self, first_name, last_name, email, password=None, **extra_fields):
        if not email:
            raise ValueError("The Email field must be set")
        email = self.normalize_email(email)
        if not first_name or not last_name:
            raise ValueError('First name and last name are required')
        username = self.generate_unique_username(first_name, last_name)
        user = self.model(email=email, username=username, first_name=first_name, last_name=last_name, **extra_fields)
        user.set_password(password)
        user.save()
        return user

    def generate_unique_username(self, first_name, last_name):
        base_username = f"{first_name.lower()}.{last_name.lower()}"
        username = base_username
        while self.model.objects.filter(username=username).exists():
            username = f"{base_username}{random.randint(1, 999)}"
        return username

    def create_superuser(self, first_name, last_name, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')
        return self.create_user(first_name, last_name, email, password, **extra_fields)
    
    

class CustomUser(AbstractUser, PermissionsMixin):
    class Roles(models.TextChoices):
        SUPERUSER = 'SUPERUSER', 'Superuser'
        ADMIN_GLOBAL = 'ADMIN_GLOBAL', 'Admin Global'
        ADMIN_TERRITORIAL = 'ADMIN_TERRITORIAL', 'Admin Territorial'
        CHEF_DEPT_TECH = 'CHEF_DEPT_TECH', 'Chef Département Technique'
        RESP_OPERATEUR = 'RESP_OPERATEUR', 'Responsable Opérateur de Saisie'

    user_permissions = models.ManyToManyField(
        Permission,
        related_name='customuser_set_permissions',
        blank=True
    )
    email = models.EmailField(unique=True)
    country = models.ForeignKey(Country, on_delete=models.SET_NULL, null=True, blank=True)
    role = models.CharField(
        max_length=32,
        choices=Roles.choices,
        default=Roles.RESP_OPERATEUR,
    )
    objects = CustomUserManager()

    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = ['first_name', 'last_name', 'email']

    def is_superuser_role(self):
        return self.role == self.Roles.SUPERUSER

    def is_admin_global(self):
        return self.role == self.Roles.ADMIN_GLOBAL

    def is_admin_territorial(self):
        return self.role == self.Roles.ADMIN_TERRITORIAL

    def is_chef_dept_tech(self):
        return self.role == self.Roles.CHEF_DEPT_TECH

    def is_responsable_operateur(self):
        return self.role == self.Roles.RESPONSABLE_OPERATEUR


class PasswordResetToken(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    token = models.UUIDField(default=uuid.uuid4, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def is_expired(self):
        now = timezone.now()
        return self.created_at < now - timezone.timedelta(hours=24)
