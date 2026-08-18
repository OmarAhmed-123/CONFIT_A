# 🚀 دليل النشر والتشغيل السحابي المجاني لمشروع CONFIT
## Production Deployment Guide (Free Tier Infrastructure)

هذا الدليل يشرح خطوة بخطوة كيفية رفع وتشغيل جميع أجزاء منصة **CONFIT** (الفرونت إند، الباك إند، قاعدة البيانات، الكاش) على سيرفرات واستضافات سحابية **مجانية 100%** مع تشغيل الذكاء الاصطناعي وغرفة القياس الافتراضية.

---

## 🏗️ المعمارية السحابية السريعة (Architecture Blueprint)

```
                       ┌──────────────────────────────┐
                       │   مستخدم المنصة (Browser)    │
                       └──────────────┬───────────────┘
                                      │
            ┌─────────────────────────┴─────────────────────────┐
            ▼                                                   ▼
┌───────────────────────┐                           ┌───────────────────────┐
│     Frontend (SPA)    │                           │     Backend (API)     │
│   استضافة: Vercel     │   API Requests (/api/v1)  │   استضافة: Render     │
│   Framework: React+TS │ ────────────────────────> │   Framework: FastAPI  │
│   CDN: Global Edge    │                           │   Python: 3.13 / 3.11 │
└───────────────────────┘                           └───────────┬───────────┘
                                                                │
                                    ┌───────────────────────────┴───────────────────────────┐
                                    ▼                                                       ▼
                        ┌───────────────────────┐                               ┌───────────────────────┐
                        │    Database (SQL)     │                               │      Redis Cache      │
                        │   استضافة: Neon.tech  │                               │   استضافة: Upstash    │
                        │   Engine: PostgreSQL  │                               │   Serverless Redis    │
                        └───────────────────────┘                               └───────────────────────┘
```

---

## 📋 الخطوات بالترتيب لتشغيل المشروع كاملاً

---

### الخطوة 1: إنشاء قاعدة بيانات PostgreSQL مجانية على (Neon.tech)

1. ادخل على الموقع: **[https://neon.tech](https://neon.tech)** وسجل دخول بحساب GitHub.
2. اضغط على **"Create Project"**.
3. أدخل البيانات:
   * **Project Name:** `confit-production-db`
   * **Region:** اختر أقرب منطقة لك (مثل `Frankfurt (eu-central-1)`).
   * **Postgres Version:** `16`.
4. اضغط **"Create Project"**.
5. ستظهر لك شاشة بعنوان **Connection Details**، انسخ الرابط المباشر.
6. احتفظ بالرابط، وسيكون شكله كالتالي:
   ```env
   DATABASE_URL="postgresql://neondb_owner:YOUR_PASSWORD@ep-cool-xyz.eu-central-1.aws.neon.tech/neondb?sslmode=require"
   ```

---

### الخطوة 2: إنشاء Redis مجاني على (Upstash) — اختياري

1. ادخل على الموقع: **[https://upstash.com](https://upstash.com)** وسجل دخول بـ GitHub.
2. اضغط **"Create Database"** واختر Serverless.
3. انسخ رابط الاتصال **`REDIS_URL`**:
   ```env
   REDIS_URL="rediss://default:YOUR_PASSWORD@eu1-cool-xyz.upstash.io:6379"
   ```

---

### الخطوة 3: نشر الباك إند (FastAPI) على Render.com

1. ادخل على الموقع: **[https://render.com](https://render.com)** وسجل دخول بـ GitHub.
2. من لوحة التحكم، اضغط **"New +"** $\rightarrow$ واختر **"Web Service"**.
3. اختر المستودع الخاص بك: **`OmarAhmed-123/CONFIT_A`**.
4. املأ الإعدادات بدقة:
   * **Name:** `confit-backend-api`
   * **Region:** `Frankfurt (EU Central)`
   * **Branch:** `main`
   * **Root Directory:** اتركه فارغاً أو `./`
   * **Runtime:** `Python 3`
   * **Build Command:** `pip install -r backend/requirements.txt`
   * **Start Command:** `uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT`
   * **Instance Type:** `Free`

5. انزل لأسفل واضغط على **"Environment Variables"** وأضف المتغيرات التالية:
   * `DATABASE_URL` = (رابط Neon من الخطوة 1)
   * `SECRET_KEY` = `confit_production_jwt_secret_key_2026_secure`
   * `JWT_REFRESH_SECRET` = `confit_production_refresh_secret_2026_secure`
   * `ENCRYPTION_KEY_FOR_BODY_DATA` = `confit_body_privacy_encryption_secret_key_32bytes!`
   * `ENVIRONMENT` = `production`
   * `DEBUG` = `false`
   * `AI_PROVIDERS` = `gemini,nvidia,openai,grok`
   * `GEMINI_API_KEY` = `YOUR_GEMINI_API_KEY`
   * `OPENAI_API_KEY` = `YOUR_OPENAI_API_KEY`
   * `GROK_API_KEY` = `YOUR_GROK_API_KEY`
   * `NVIDIA_API_KEY` = `YOUR_NVIDIA_API_KEY`
   * `KLING_API_KEY` = `YOUR_KLING_API_KEY`

6. اضغط **"Create Web Service"**.
7. ستحصل على رابط السيرفر العام، مثل:
   `https://confit-backend-api.onrender.com`

8. **تغذية قاعدة البيانات بالمنتجات (Database Seeding):**
   * من لوحة تحكم الخدمة في Render، اضغط على تبويب **"Shell"** واكتب الأمر التالي:
     ```bash
     PYTHONPATH=. python3 backend/app/seed_data.py
     ```
   * ستظهر رسالة: `✅ CONFIT Database Seeded Successfully with 24+ items!`

---

### الخطوة 4: نشر الفرونت إند (React + Vite) على Vercel

1. ادخل على الموقع: **[https://vercel.com](https://vercel.com)** وسجل دخول بـ GitHub.
2. اضغط **"Add New..."** $\rightarrow$ **"Project"**.
3. اختر مستودع **`CONFIT_A`** واضغط **Import**.
4. في شاشة الإعدادات:
   * **Framework Preset:** `Vite`.
   * **Root Directory:** اضغط **Edit** وحدد مجلد **`frontend`**.
   * **Build Command:** `npm run build`
   * **Output Directory:** `dist`
5. في قسم **"Environment Variables"** أضف:
   * **Key:** `VITE_API_URL`
   * **Value:** `https://confit-backend-api.onrender.com/api/v1` *(ضع رابط الـ Render الخاص بك)*
6. اضغط **"Deploy"**.
7. سيكتمل البناء ويكون موقعك لايف برابط سريع مثل:
   `https://confit-a.vercel.app`

---

## 🧪 التحقق من عمل جميع أجزاء النظام (Post-Deployment Verification)

1. **فحص الـ API Health:**
   افتح الرابط: `https://confit-backend-api.onrender.com/api/v1/health`
   ستظهر لك رسالة: `{"status": "healthy", "version": "1.0.0"}`
2. **فحص وثائق الـ OpenAPI (Swagger):**
   افتح: `https://confit-backend-api.onrender.com/docs`
3. **فحص الموقع العام:**
   افتح رابط الـ Vercel، تصفح المنتجات، جرب غرفة القياس الافتراضية (Dynamic Try-On)، واسحب القطع وأسقطها على الشخص لمعاينة التلبيس الحقيقي.

---

## 🔒 حسابات الدخول الافتراضية للتجربة (Pre-seeded Accounts)

* **حساب العميل (Shopper):**
  * Email: `shopper@confit.io`
  * Password: `Password123!`
* **حساب الأدمن العام (Admin Portal):**
  * Email: `admin@confit.io`
  * Password: `Password123!`
* **حساب مدير البراند (Massimo Dutti Brand Manager):**
  * Email: `brand@massimodutti.com`
  * Password: `Password123!`
