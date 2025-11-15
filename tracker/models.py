from django.db import models

class UpdateCache(models.Model):
    library = models.CharField(max_length=200, unique=True)
    version = models.CharField(max_length=100)
    release_date = models.CharField(max_length=50, blank=True)
    category = models.CharField(max_length=10, choices=[("major","major"),("minor","minor")])
    summary = models.TextField(blank=True)
    source = models.URLField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.library} -> {self.version} ({self.category})"
