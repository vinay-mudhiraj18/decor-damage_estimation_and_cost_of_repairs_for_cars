import os
import uuid
import json
from io import BytesIO
from PIL import Image
import cv2
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
    # Fetch distinct brand and model combinations in a single query
    brand_models_qs = list(CarModel.objects.values('brand', 'model').distinct())
    
    # Deriving distinct brands list in memory to avoid a second database query
    brands = sorted(list(set(item['brand'] for item in brand_models_qs)))
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

        uid = uuid.uuid4().hex[:8]
        merged = {}          # part_name → best detection info
        first_upload_bytes = None
        first_upload_name  = None
        last_detected_bytes = None
        last_detected_name  = None

        for idx, f in enumerate(image_files):
            # Read uploaded file into memory
            img_bytes = f.read()

            # Load image into memory as a PIL Image
            try:
                pil_img = Image.open(BytesIO(img_bytes)).convert("RGB")
            except Exception:
                continue

            # Optimize image size (scale down to max 1024px to speed up CPU inference & S3 upload times)
            max_size = 1024
            if max(pil_img.size) > max_size:
                pil_img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
                opt_buffer = BytesIO()
                pil_img.save(opt_buffer, format="JPEG", quality=85)
                img_bytes = opt_buffer.getvalue()

            if idx == 0:
                first_upload_bytes = img_bytes
                first_upload_name  = f'original_{uid}.jpg'

            # Run YOLO directly on the PIL Image in-memory
            result = model(pil_img)
            boxes  = result[0].boxes

            if not boxes or len(boxes) == 0:
                continue

            # Plot annotated results in-memory (returns BGR numpy array)
            annotated_bgr = result[0].plot()
            annotated_rgb = cv2.cvtColor(annotated_bgr, cv2.COLOR_BGR2RGB)
            
            # Save PIL Image directly to in-memory bytes buffer with optimized quality
            annotated_pil = Image.fromarray(annotated_rgb)
            ann_buffer = BytesIO()
            annotated_pil.save(ann_buffer, format="JPEG", quality=85)
            
            last_detected_bytes = ann_buffer.getvalue()
            last_detected_name = f'detected_{uid}_{idx}.jpg'

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

        # Build final part_details with prices in a single query (batch fetch instead of loop)
        part_details = {}
        rows = CarModel.objects.filter(brand=car_brand, model=car_model_val, part__in=merged.keys())
        for row in rows:
            info = merged[row.part]
            part_details[row.part] = {
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
    # Convert query set to a list once to load all reports in a single query
    reports = list(DetectionReport.objects.filter(user=request.user).order_by('-created_at'))
    total = len(reports)
    
    # Calculate statistics in memory (0 extra database queries)
    total_cost_sum = sum(float(r.total_cost) for r in reports)
    avg_cost = round(total_cost_sum / total, 0) if total else 0
    with_damage = sum(1 for r in reports if r.total_cost > 0)
    
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


import math
import urllib.request
import urllib.parse
from django.http import JsonResponse

def dist_km(lat1, lon1, lat2, lon2):
    r = 6371
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = math.sin(d_lat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon/2)**2
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

@login_required
def nearby_garages(request):
    return render(request, 'nearby_garages.html', {
        'google_maps_api_key': getattr(settings, 'GOOGLE_MAPS_API_KEY', '')
    })

import time

# In-memory cache for nearby garages (rounded coordinates grid -> (timestamp, garages_list))
GARAGES_CACHE = {}
CACHE_EXPIRY = 300  # 5 minutes cache

@login_required
def nearby_garages_api(request):
    lat_str = request.GET.get('lat')
    lng_str = request.GET.get('lng')
    
    if not lat_str or not lng_str:
        return JsonResponse({'error': 'Latitude and longitude are required.'}, status=400)
        
    try:
        lat = float(lat_str)
        lng = float(lng_str)
    except ValueError:
        return JsonResponse({'error': 'Invalid latitude or longitude.'}, status=400)
        
    # In-memory cache check: round to 2 decimal places (~1.1 km accuracy)
    cache_key = (round(lat, 2), round(lng, 2))
    now = time.time()
    if cache_key in GARAGES_CACHE:
        cache_time, cached_data = GARAGES_CACHE[cache_key]
        if now - cache_time < CACHE_EXPIRY:
            return JsonResponse({
                'garages': cached_data['garages'],
                'radius_used': cached_data['radius_used'],
                'source': 'cache'
            })
            
    overpass_endpoints = [
        "https://overpass-api.de/api/interpreter",
        "https://lz4.overpass-api.de/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter"
    ]
    
    # Sequentially check expanding search radii until we find at least 10 garages
    radii = [5000, 10000, 25000, 50000, 100000]
    
    for radius in radii:
        q = f"""[out:json][timeout:5];
        (
          node["amenity"="car_repair"](around:{radius},{lat},{lng});
          way["amenity"="car_repair"](around:{radius},{lat},{lng});
          relation["amenity"="car_repair"](around:{radius},{lat},{lng});
          node["shop"="car_repair"](around:{radius},{lat},{lng});
          way["shop"="car_repair"](around:{radius},{lat},{lng});
          node["shop"="car"](around:{radius},{lat},{lng});
        );
        out center;"""
        
        data = urllib.parse.urlencode({'data': q}).encode('utf-8')
        
        for endpoint in overpass_endpoints:
            try:
                req = urllib.request.Request(
                    endpoint,
                    data=data,
                    headers={'User-Agent': 'DECOR_CarRepairLocator/1.0 (vinay-mudhiraj18/decor)'}
                )
                with urllib.request.urlopen(req, timeout=2.5) as response:
                    if response.status == 200:
                        raw_data = response.read().decode('utf-8')
                        result_json = json.loads(raw_data)
                        elements = result_json.get('elements', [])
                        
                        parsed_garages = []
                        for el in elements:
                            el_lat = el.get('lat') or (el.get('center', {}).get('lat') if el.get('center') else None)
                            el_lng = el.get('lon') or (el.get('center', {}).get('lon') if el.get('center') else None)
                            if not el_lat or not el_lng:
                                continue
                            tags = el.get('tags', {})
                            tp = tags.get('amenity') or tags.get('shop') or ''
                            tl = 'Car Repair' if tp in ['car_repair', 'vehicle_repair'] else ('Car Shop' if tp == 'car' else tp.replace('_', ' ').title())
                            street = tags.get('addr:street', '')
                            house = tags.get('addr:housenumber', '')
                            city = tags.get('addr:city', '')
                            address_parts = [p for p in [house, street, city] if p]
                            address = ", ".join(address_parts) if address_parts else f"Near {lat_str}, {lng_str}"
                            
                            parsed_garages.append({
                                'id': str(el.get('id')),
                                'lat': el_lat,
                                'lng': el_lng,
                                'name': tags.get('name') or tags.get('name:en') or 'Unnamed Car Repair',
                                'phone': tags.get('phone') or tags.get('contact:phone') or '+91 98765 43210',
                                'address': address,
                                'type': tl,
                                'rating': round(4.0 + (int(el.get('id', 0)) % 10) / 10.0, 1)
                            })
                        
                        # Sort by distance
                        for pg in parsed_garages:
                            pg['distance'] = dist_km(lat, lng, pg['lat'], pg['lng'])
                        parsed_garages.sort(key=lambda x: x['distance'])
                        
                        # Deduplicate by name
                        seen_names = set()
                        unique_garages = []
                        for pg in parsed_garages:
                            if pg['name'] not in seen_names:
                                seen_names.add(pg['name'])
                                unique_garages.append(pg)
                        
                        # If we have found at least 10 unique garages OR we reached the max 100km radius, return them!
                        if len(unique_garages) >= 10 or radius == radii[-1]:
                            # Cache the result for next 5 minutes
                            cached_payload = {
                                'garages': unique_garages[:15],
                                'radius_used': radius
                            }
                            GARAGES_CACHE[cache_key] = (now, cached_payload)
                            return JsonResponse({
                                'garages': unique_garages[:15],
                                'radius_used': radius,
                                'source': 'osm'
                            })
                        else:
                            # Break this endpoint loop to search the next larger radius
                            break
            except Exception as e:
                print(f"[DECOR] Overpass endpoint {endpoint} failed for radius {radius}m: {e}")
                continue
                
    return JsonResponse({'garages': [], 'radius_used': 0, 'source': 'none'})
