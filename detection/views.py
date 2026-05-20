import os
import uuid
import json
from io import BytesIO
from django.core.files.base import ContentFile
from django.utils import timezone
from django.shortcuts import render, redirect
from django.conf import settings
from django.contrib import messages, auth
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from ultralytics import YOLO
from .models import CarModel, DetectionReport

# ── YOLO model (loaded once) ──────────────────────────────────────────────────
model = YOLO(settings.YOLO_MODEL_PATH)

CLASS_NAMES = ['Bonnet', 'Bumper', 'Dickey', 'Door', 'Fender', 'Light', 'Windshield']


def get_part_name(class_id):
    if 0 <= int(class_id) < len(CLASS_NAMES):
        return CLASS_NAMES[int(class_id)]
    return None


# ── Auth views ────────────────────────────────────────────────────────────────

def landing_page(request):
    """Public landing page — always shown at /."""
    return render(request, 'landing_page.html')


def register_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')  # goes to /dashboard/

    COMMON_PASSWORDS = {
        'password', 'password1', 'password123', '123456789', '12345678',
        'qwerty123', 'iloveyou', 'admin1234', 'letmein1', 'welcome1',
        'monkey123', 'dragon123', 'master123', 'sunshine1', 'princess1',
        'football', 'shadow123', 'superman1', 'michael1', 'charlie1',
    }

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        email    = request.POST.get('email', '').strip().lower()
        password = request.POST.get('password', '')
        confirm  = request.POST.get('confirm', '')

        error = None
        if not username or not email or not password:
            error = 'All fields are required.'
        elif len(username) < 3:
            error = 'Username must be at least 3 characters.'
        elif not username.replace('_', '').replace('.', '').isalnum():
            error = 'Username may only contain letters, numbers, underscores and dots.'
        elif password != confirm:
            error = 'Passwords do not match.'
        elif User.objects.filter(username=username).exists():
            error = 'Username already taken.'
        elif User.objects.filter(email=email).exists():
            error = 'An account with this email already exists.'
        elif len(password) < 12:
            error = 'Password must be at least 12 characters.'
        elif len(password) > 128:
            error = 'Password must be under 128 characters.'
        elif ' ' in password:
            error = 'Password must not contain spaces.'
        elif not any(c.isupper() for c in password):
            error = 'Password must contain at least one uppercase letter.'
        elif not any(c.islower() for c in password):
            error = 'Password must contain at least one lowercase letter.'
        elif not any(c.isdigit() for c in password):
            error = 'Password must contain at least one number.'
        elif not any(c in '!@#$%^&*()_+-=[]{}|;:,.<>?' for c in password):
            error = 'Password must contain at least one special character.'
        elif username.lower() in password.lower():
            error = 'Password must not contain your username.'
        elif password.lower() in COMMON_PASSWORDS:
            error = 'Password is too common. Please choose a stronger one.'
        
        if error:
            messages.error(request, error)
        else:
            User.objects.create_user(username=username, email=email, password=password)
            messages.success(request, 'Account created! Please log in.')
            return redirect('login')
    return render(request, 'register.html')


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        user = auth.authenticate(
            request,
            username=request.POST.get('username', '').strip(),
            password=request.POST.get('password', ''),
        )
        if user:
            auth.login(request, user)
            return redirect('landing')
        messages.error(request, 'Invalid username or password.')
    return render(request, 'login.html')


def logout_view(request):
    auth.logout(request)
    return redirect('login')


# ── Main app views (login required) ──────────────────────────────────────────

@login_required
def dashboard(request):
    brands = list(CarModel.objects.values_list('brand', flat=True).distinct())
    brand_models_qs = list(CarModel.objects.values('brand', 'model').distinct())
    brand_models = json.dumps(brand_models_qs)

    if request.method == 'POST':
        car_brand     = request.POST.get('carBrand')
        car_model_val = request.POST.get('carModel')
        image_files   = request.FILES.getlist('images')

        if not image_files:
            messages.error(request, 'Please upload at least one image.')
            return render(request, 'dashboard.html', {'brands': brands, 'brand_models': brand_models})

        for f in image_files:
            if not f.name.lower().endswith(('.png', '.jpg', '.jpeg')):
                messages.error(request, f'Invalid file: {f.name}')
                return render(request, 'dashboard.html', {'brands': brands, 'brand_models': brand_models})

        process_dir = settings.MEDIA_ROOT
        os.makedirs(process_dir, exist_ok=True)

        uid = uuid.uuid4().hex[:8]
        merged = {}          # part_name → best detection info
        first_upload_bytes = None
        first_upload_name  = None
        last_detected_bytes = None
        last_detected_name  = None

        for idx, f in enumerate(image_files):
            # Read uploaded file into memory
            img_bytes = f.read()

            if idx == 0:
                first_upload_bytes = img_bytes
                first_upload_name  = f'original_{uid}.jpg'

            # Save temporarily to disk so YOLO can process it
            tmp_path = os.path.join(process_dir, f'tmp_{uid}_{idx}.jpg')
            with open(tmp_path, 'wb') as out:
                out.write(img_bytes)

            result = model(tmp_path)
            boxes  = result[0].boxes

            # Clean up temp file
            try:
                os.remove(tmp_path)
            except OSError:
                pass

            if not boxes or len(boxes) == 0:
                continue

            # Save annotated image to memory
            annotated_tmp = os.path.join(process_dir, f'ann_{uid}_{idx}.jpg')
            result[0].save(annotated_tmp)
            with open(annotated_tmp, 'rb') as af:
                last_detected_bytes = af.read()
            last_detected_name = f'detected_{uid}_{idx}.jpg'
            try:
                os.remove(annotated_tmp)
            except OSError:
                pass

            for box in boxes:
                class_id = int(box.cls.item())
                conf     = float(box.conf.item())
                part     = get_part_name(class_id)
                if not part:
                    continue
                if part in merged and conf <= merged[part]['_conf']:
                    continue
                merged[part] = {
                    '_conf':      conf,
                    'confidence': round(conf * 100, 1),
                }

        if not merged:
            report = DetectionReport.objects.create(
                user=request.user,
                car_brand=car_brand,
                car_model=car_model_val,
                results={},
                total_cost=0,
            )
            if first_upload_bytes:
                report.original_image.save(first_upload_name, ContentFile(first_upload_bytes), save=True)
            return render(request, 'estimate.html', {
                'original_image_url': report.original_image.url if report.original_image else None,
                'car_brand': car_brand,
                'car_model': car_model_val,
                'damage_detected': False,
            })

        # Build final part_details with prices
        part_details = {}
        for part, info in merged.items():
            row = CarModel.objects.filter(brand=car_brand, model=car_model_val, part=part).first()
            if row:
                part_details[part] = {
                    'confidence': info['confidence'],
                    'price':      float(row.price),
                }

        total_cost = round(sum(d['price'] for d in part_details.values()), 2)

        # Find existing report with same user + vehicle + parts, just update timestamp & images
        existing = DetectionReport.objects.filter(
            user=request.user,
            car_brand=car_brand,
            car_model=car_model_val,
            total_cost=total_cost,
        ).order_by('-created_at').first()

        if existing and existing.results == part_details:
            # Same result — update images and refresh timestamp
            existing.created_at = timezone.now()
            existing.save(update_fields=['created_at'])
            if first_upload_bytes:
                existing.original_image.save(f'original_{uid}.jpg', ContentFile(first_upload_bytes), save=True)
            if last_detected_bytes:
                existing.detected_image.save(f'detected_{uid}.jpg', ContentFile(last_detected_bytes), save=True)
            report = existing
        else:
            report = DetectionReport.objects.create(
                user=request.user,
                car_brand=car_brand,
                car_model=car_model_val,
                results=part_details,
                total_cost=total_cost,
            )
            if first_upload_bytes:
                report.original_image.save(f'original_{uid}.jpg', ContentFile(first_upload_bytes), save=True)
            if last_detected_bytes:
                report.detected_image.save(f'detected_{uid}.jpg', ContentFile(last_detected_bytes), save=True)

        return render(request, 'estimate.html', {
            'original_image_url': report.original_image.url if report.original_image else None,
            'detected_image_url': report.detected_image.url if report.detected_image else None,
            'part_details':    part_details,
            'car_brand':       car_brand,
            'car_model':       car_model_val,
            'damage_detected': True,
            'total_cost':      total_cost,
            'image_count':     len(image_files),
        })

    return render(request, 'dashboard.html', {'brands': brands, 'brand_models': brand_models})


@login_required
def report_history(request):
    reports = DetectionReport.objects.filter(user=request.user).order_by('-created_at')
    total = reports.count()
    avg_cost = round(sum(float(r.total_cost) for r in reports) / total, 0) if total else 0
    with_damage = reports.filter(total_cost__gt=0).count()
    return render(request, 'report_history.html', {
        'reports': reports,
        'total_inspections': total,
        'avg_cost': int(avg_cost),
        'with_damage': with_damage,
    })


@login_required
def report_detail(request, pk):
    from django.shortcuts import get_object_or_404
    report = get_object_or_404(DetectionReport, pk=pk, user=request.user)
    return render(request, 'report_detail.html', {'report': report})


@login_required
def nearby_garages(request):
    return render(request, 'nearby_garages.html', {
        'google_maps_api_key': getattr(settings, 'GOOGLE_MAPS_API_KEY', '')
    })
