from django.contrib import admin
from .models import DetectionReport, CarModel


@admin.register(DetectionReport)
class DetectionReportAdmin(admin.ModelAdmin):
    list_display  = ('id', 'user', 'car_brand', 'car_model', 'total_cost', 'created_at')
    list_filter   = ('car_brand', 'car_model', 'created_at')
    search_fields = ('user__username', 'user__email', 'car_brand', 'car_model')
    ordering      = ('-created_at',)
    readonly_fields = ('results', 'original_image', 'detected_image', 'created_at')

    # Allow delete from list and detail view
    actions = ['delete_selected']

    def has_delete_permission(self, request, obj=None):
        return request.user.is_staff

    def has_change_permission(self, request, obj=None):
        return request.user.is_staff

    def has_add_permission(self, request):
        return False  # reports are created by the app, not manually


@admin.register(CarModel)
class CarModelAdmin(admin.ModelAdmin):
    list_display  = ('brand', 'model', 'part', 'price')
    list_filter   = ('brand', 'model')
    search_fields = ('brand', 'model', 'part')
    ordering      = ('brand', 'model', 'part')
