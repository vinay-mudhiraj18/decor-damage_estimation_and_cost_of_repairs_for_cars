# DECOR — Damage Estimation and Cost Of Repairs

A Django web application that uses a custom-trained YOLOv11 model to detect damaged parts on a vehicle from uploaded images and generate a repair cost estimate.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Web Framework | Django 5.2 |
| AI / Detection | YOLOv11 (Ultralytics) |
| Database | SQLite (dev) / MySQL (prod) |
| Frontend | HTML, CSS, Vanilla JS |
| Image Processing | Pillow, OpenCV |
| Auth | Django built-in auth |
| Config | python-dotenv |

---

## Detectable Parts

The model detects damage on 7 vehicle parts:

| Class ID | Part |
|---|---|
| 0 | Bonnet |
| 1 | Bumper |
| 2 | Dickey (boot/trunk) |
| 3 | Door |
| 4 | Fender |
| 5 | Light |
| 6 | Windshield |

---

## Project Structure

```
decor/
├── manage.py
├── .env
├── requirements.txt
├── db.sqlite3
│
├── core/                          # Django project config
│   ├── settings.py
│   ├── urls.py
│   ├── wsgi.py
│   └── asgi.py
│
├── detection/                     # Main application
│   ├── views.py                   # All business logic
│   ├── models.py                  # CarModel, DetectionReport
│   ├── urls.py                    # URL routing
│   ├── admin.py
│   ├── migrations/
│   └── templates/
│       ├── login.html
│       ├── register.html
│       ├── dashboard.html
│       ├── estimate.html
│       ├── report_history.html
│       └── report_detail.html
│
├── models/
│   └── model weights/
│       └── best_yolo_v11.pt       # Trained YOLOv11 weights
│
├── static/
│   └── logo.png
│
└── media/                         # User-uploaded & annotated images (auto-created)
    └── reports/
        ├── original/
        └── detected/
```

---

## Setup & Installation

### 1. Clone and install

```bash
git clone <repo-url>
cd decor
pip install -r requirements.txt
```

### 2. Configure `.env`

```env
SECRET_KEY=your-django-secret-key
DEBUG=True
```

### 3. Run migrations

```bash
python manage.py migrate
```

### 4. Start the server

```bash
python manage.py runserver
```

Open http://127.0.0.1:8000/

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        CLIENT BROWSER                        │
│         HTML/CSS/JS  ·  Form Submissions  ·  File Upload     │
└───────────────────────────────┬─────────────────────────────┘
                                │ HTTP Request
                                ▼
┌─────────────────────────────────────────────────────────────┐
│                      DJANGO WEB SERVER                       │
│                                                              │
│  ┌─────────────┐   ┌──────────────┐   ┌──────────────────┐  │
│  │  URL Router │──▶│    Views     │──▶│    Templates     │  │
│  │  (urls.py)  │   │  (views.py)  │   │   (HTML pages)   │  │
│  └─────────────┘   └──────┬───────┘   └──────────────────┘  │
│                           │                                  │
│              ┌────────────┼────────────┐                     │
│              ▼            ▼            ▼                     │
│  ┌──────────────┐  ┌──────────┐  ┌──────────────────────┐   │
│  │  Django Auth │  │  YOLO    │  │   Django ORM         │   │
│  │  (register,  │  │  Model   │  │   (CarModel,         │   │
│  │   login)     │  │ Inference│  │    DetectionReport,  │   │
│  └──────────────┘  └──────────┘  │    User)             │   │
│                                  └──────────┬───────────┘   │
└─────────────────────────────────────────────┼───────────────┘
                                              │
                    ┌─────────────────────────┼──────────────┐
                    │         DATABASE         │              │
                    │                          ▼              │
                    │  ┌──────────┐  ┌──────────────────┐    │
                    │  │  Users   │  │  DetectionReport │    │
                    │  │ (Django) │  │  CarModel        │    │
                    │  └──────────┘  └──────────────────┘    │
                    └────────────────────────────────────────┘
                                              │
                    ┌─────────────────────────┼──────────────┐
                    │       MEDIA STORAGE      │              │
                    │   media/reports/original/              │
                    │   media/reports/detected/              │
                    └────────────────────────────────────────┘
```

---

## Data Flow

### Level 0 — Context Diagram

```
                        ┌─────────────────────────┐
                        │                         │
  User ────[image +────▶│        DECOR            │────[estimate +]────▶ User
           car info]    │   (Detection System)    │     report
                        │                         │
                        └─────────────────────────┘
                                    │
                          [stores reports]
                                    │
                                    ▼
                              Database / Media
```

### Level 1 — System Data Flow

```
  User
   │
   │  1. Register / Login
   ▼
┌──────────────────┐
│   Auth Module    │──── validates credentials ────▶ Django User DB
└──────────────────┘
   │
   │  2. Upload image(s) + select car brand/model
   ▼
┌──────────────────┐
│  Dashboard View  │──── reads brands/models ──────▶ CarModel DB
└──────────────────┘
   │
   │  3. Image bytes
   ▼
┌──────────────────┐
│  Image Handler   │──── writes temp file to disk (YOLO needs file path)
└──────────────────┘
   │
   │  4. Temp file path
   ▼
┌──────────────────┐
│   YOLOv11 Model  │──── runs inference ────────────▶ bounding boxes + class IDs + confidence scores
└──────────────────┘
   │
   │  5. Detected class IDs
   ▼
┌──────────────────┐
│  Part Resolver   │──── maps class ID → part name (CLASS_NAMES list)
└──────────────────┘
   │
   │  6. Part names
   ▼
┌──────────────────┐
│  Price Lookup    │──── queries CarModel table ────▶ base repair price per part
└──────────────────┘
   │
   │  7. Part + price data
   ▼
┌──────────────────┐
│ Duplicate Check  │──── queries DetectionReport ──▶ same user + brand + model + parts?
└──────────────────┘         │                              │
                        [new result]                 [existing result]
                             │                              │
                             ▼                              ▼
                      create new report            update timestamp only
                             │
                             ▼
┌──────────────────┐
│  Image Storage   │──── saves original + annotated images to media/reports/
└──────────────────┘
   │
   │  8. Report saved
   ▼
┌──────────────────┐
│  Estimate Page   │──── renders part table + images + total cost ──▶ User
└──────────────────┘
```

---

## Algorithm / Workflow

### 1. User Authentication

```
Register:
  input: username, email, password, confirm
  validate:
    - all fields present
    - passwords match
    - username not taken (User table)
    - email not taken (User table)
    - password >= 8 chars
    - contains uppercase, lowercase, digit, special char
  output: account created → auto login → redirect dashboard

Login:
  input: username, password
  validate: Django authenticate()
  output: session created → redirect dashboard
```

### 2. Image Ingestion

```
for each uploaded image file:
  1. read bytes into memory
  2. write to temp path on disk  (YOLO requires a file path)
  3. run YOLO inference on temp path
  4. delete temp file immediately after inference
  5. if detections found:
       save annotated image to temp path
       read annotated bytes into memory
       delete annotated temp file
```

### 3. YOLO Detection & Part Merging

```
for each bounding box in result:
  class_id  = box.cls          → integer 0–6
  confidence = box.conf        → float 0.0–1.0
  part_name = CLASS_NAMES[class_id]

  if part already seen in this session:
    keep only the detection with highest confidence
    (best-confidence-wins merge strategy)

output: merged dict { part_name → { confidence } }
```

### 4. Price Calculation

```
for each detected part:
  query CarModel WHERE brand = selected_brand
                   AND model = selected_model
                   AND part  = detected_part

  repair_price = row.price   (flat base price from DB, no multiplier)

total_cost = sum of all repair prices
```

### 5. Duplicate Prevention

```
query DetectionReport WHERE:
  user       = current user
  car_brand  = selected brand
  car_model  = selected model
  total_cost = calculated total

if found AND results JSON == current part_details:
  → update existing record:
      created_at = now()
      replace original_image
      replace detected_image
  → no new row created

else:
  → create new DetectionReport row
  → save images to media/reports/original/ and media/reports/detected/
```

### 6. Report History

```
query DetectionReport WHERE user = current user
order by created_at DESC

each row is clickable → report_detail view
report_detail: fetches by pk WHERE user = current user (ownership enforced)
displays: original image, annotated image, parts table, total cost, date
```

---

## Database Schema

### `car_models` (CarModel)

| Column | Type | Description |
|---|---|---|
| id | INT PK | Auto primary key |
| brand | VARCHAR(100) | Car brand e.g. Toyota |
| model | VARCHAR(100) | Car model e.g. Camry |
| part | VARCHAR(100) | Part name e.g. Bumper |
| price | DECIMAL(10,2) | Base repair price in ₹ |

### `detection_detectionreport` (DetectionReport)

| Column | Type | Description |
|---|---|---|
| id | INT PK | Auto primary key |
| user_id | FK → auth_user | Report owner |
| car_brand | VARCHAR(100) | Selected brand |
| car_model | VARCHAR(100) | Selected model |
| original_image | ImageField | Uploaded image path |
| detected_image | ImageField | YOLO-annotated image path |
| results | JSONField | `{ part: { confidence, price } }` |
| total_cost | DECIMAL(10,2) | Sum of all part prices |
| created_at | DateTimeField | Created / last updated |

### `auth_user` (Django built-in)

| Column | Description |
|---|---|
| username | Unique username |
| email | Unique email |
| password | Hashed (PBKDF2) |

---

## Notes

- The YOLO model file must be present at `models/model weights/best_yolo_v11.pt`
- Supported image formats: `.jpg`, `.jpeg`, `.png`
- Images are stored in `media/` via Django's `ImageField`, not in `static/`
- Duplicate reports (same user, same car, same detected parts) update the timestamp only — no new row is inserted
