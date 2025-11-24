from django.db import models

UPDATE_CATEGORY_CHOICES = [
    ("major", "major"),
    ("minor", "minor"),
    ("future", "future"),
]


class UpdateCache(models.Model):
    library = models.CharField(max_length=200, unique=True)
    version = models.CharField(max_length=100)
    release_date = models.CharField(max_length=50, blank=True)
    category = models.CharField(max_length=10, choices=UPDATE_CATEGORY_CHOICES)
    summary = models.TextField(blank=True)
    source = models.URLField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.library} -> {self.version} ({self.category})"
