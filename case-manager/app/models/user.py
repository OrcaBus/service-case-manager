from django.db import models

from app.fields import OrcaBusIdField
from app.models.base import BaseModel, BaseManager


class UserManager(BaseManager):
    pass


class User(BaseModel):
    objects = UserManager()
    orcabus_id = OrcaBusIdField(primary_key=True)
    email = models.EmailField(unique=True, blank=False, null=False)

    name = models.CharField(
        blank=True,
        null=True,
    )
