from django.db import models
from django.contrib.auth.models import User

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    weight = models.FloatField(null=True, blank=True)
    preferred_distance = models.FloatField(null=True, blank=True)
    preferred_cycle = models.IntegerField(null=True, blank=True)
    prefers_facilities = models.BooleanField(default=False)
    edit_count = models.IntegerField(default=0)

    def __str__(self):
        return self.user.username
