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
