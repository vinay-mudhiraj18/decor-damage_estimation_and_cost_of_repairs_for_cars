from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User


class CarModel(models.Model):
    brand = models.CharField(max_length=100)
    model = models.CharField(max_length=100)
    part = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        db_table = 'car_models'

    def __str__(self):
        return f"{self.brand} {self.model} - {self.part}"


class DetectionReport(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    car_brand = models.CharField(max_length=100)
    car_model = models.CharField(max_length=100)
    original_image = models.ImageField(upload_to='reports/original/', blank=True, null=True)
    detected_image = models.ImageField(upload_to='reports/detected/', blank=True, null=True)
    results = models.JSONField()
    total_cost = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.user.username} | {self.car_brand} {self.car_model} | ₹{self.total_cost}"


# ── Signals for Auto-Cleaning Storage on Deletion ──────────────────────────────
from django.db.models.signals import post_delete
from django.dispatch import receiver

@receiver(post_delete, sender=DetectionReport)
def auto_delete_images_on_report_delete(sender, instance, **kwargs):
    """
    Automatically deletes original and detected image files from S3/Supabase Storage
    when the corresponding DetectionReport is deleted (either directly or via cascading user deletion).
    """
    if instance.original_image:
        try:
            instance.original_image.delete(save=False)
        except Exception as e:
            # Prevent failures in storage deletion from blocking database operations
            pass

    if instance.detected_image:
        try:
            instance.detected_image.delete(save=False)
        except Exception as e:
            pass

