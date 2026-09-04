# 🔑 قائمة المفاتيح والمتغيرات البيئية الكاملة لمشروع CONFIT
## Production Environment Variables & API Keys Reference

هذا الملف يحتوي على كافة المفاتيح والمتغيرات البيئية (Environment Variables) التي تحتاج إلى نسخها ولصقها في إعدادات السيرفرات (Vercel و Render و Neon) أثناء عملية النشر السحابي.

---

## 1️⃣ مفاتيح الفرونت إند (Frontend - Vercel Environment Variables)

توضع هذه المفاتيح في لوحة تحكم **Vercel** في قسم:
`Project Settings` $\rightarrow$ `Environment Variables`

| اسم المتغير (Key) | القيمة المقترحة (Value) | الشرح والغرض |
|---|---|---|
| `VITE_API_URL` | `https://confit-backend-api.onrender.com/api/v1` | رابط سيرفر الباك إند على Render لاستقبال طلبات الـ API. |
| `VITE_APP_NAME` | `CONFIT` | اسم المنصة التجاري. |
| `VITE_DEFAULT_MARKET` | `EG` | السوق الافتراضي للمنصة (`EG` لمصر، `AE` للإمارات، `SA` للسعودية). |
| `VITE_ENABLE_TRYON_MOTION` | `true` | تفعيل ميزة الحركة وتسلسل التلبيس في غرفة القياس. |

---

## 2️⃣ مفاتيح الباك إند (Backend - Render.com Environment Variables)

توضع هذه المفاتيح في لوحة تحكم **Render.com** في إعدادات الـ Web Service في قسم:
`Environment` $\rightarrow$ `Add Environment Variable`

### أ) مفاتيح الأمان والتشفير (Security & Encryption)
| اسم المتغير (Key) | القيمة (Value) | الشرح |
|---|---|---|
| `SECRET_KEY` | `<generate: python -c "import secrets;print(secrets.token_urlsafe(48))">` | مفتاح توقيع وتشفير توكنات تسجيل الدخول (JWT Access Tokens). |
| `JWT_REFRESH_SECRET` | `<generate a second, different random value>` | مفتاح تدوير وتجديد توكنات الجلسة (Refresh Token Rotation). |
| `ALGORITHM` | `HS256` | خوارزمية تشفير التوكن. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `1440` | مدة صلاحية توكن الدخول (24 ساعة = 1440 دقيقة). |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `30` | مدة صلاحية توكن التجديد (30 يوماً). |
| `ENCRYPTION_KEY_FOR_BODY_DATA` | `<generate a third random value, >= 32 chars>` | مفتاح تشفير القياسات الحيوية بقفل **Fernet-256 AES**. |

---

### ب) مفاتيح قاعدة البيانات والربط (Database & Core Config)
| اسم المتغير (Key) | القيمة (Value) | الشرح |
|---|---|---|
| `DATABASE_URL` | `postgresql://neondb_owner:YOUR_PASSWORD@ep-xyz.neon.tech/neondb?sslmode=require` | رابط الاتصال بقاعدة بيانات PostgreSQL السحابية من Neon.tech. |
| `REDIS_URL` | `rediss://default:YOUR_PASSWORD@eu1-xyz.upstash.io:6379` | رابط الاتصال بـ Redis من Upstash للكاش ومهام Celery. |
| `ENVIRONMENT` | `production` | بيئة التشغيل الإنتاجية. |
| `DEBUG` | `false` | إيقاف وضع التصحيح في الإنتاج لزيادة الأمان والسرعة. |
| `PORT` | `8000` | المنفذ الافتراضي للـ API. |

---

### ج) مفاتيح الذكاء الاصطناعي ومحركات التنسيق (AI & VTON Provider Keys)
| اسم المتغير (Key) | القيمة (Value) | الشرح |
|---|---|---|
| `AI_PROVIDERS` | `gemini,nvidia,openai,grok` | سلسلة الفيل-أوفر (Failover Chain) المعتمدة لمحرك الستايلست. |
| `GEMINI_API_KEY` | `YOUR_GEMINI_API_KEY` | مفتاح Google Gemini Flash لتوليد نصائح التنسيق السريعة. |
| `OPENAI_API_KEY` | `YOUR_OPENAI_API_KEY` | مفتاح OpenAI GPT-4o-mini للمحادثة الذكية وتحليل النوايا. |
| `GROK_API_KEY` | `YOUR_GROK_API_KEY` | مفتاح Groq LLaMA-3.3 لتسريع استجابة المساعد الذكي. |
| `NVIDIA_API_KEY` | `YOUR_NVIDIA_API_KEY` | مفتاح NVIDIA NIM Llama 3.1-70B للتنسيق المتقدم. |
| `NVIDIA_CHAT_KEY_2` | `YOUR_NVIDIA_NEMOTRON_KEY` | مفتاح NVIDIA Nemotron-12B للرؤية الحاسوبية وتحليل الصور. |
| `KLING_API_KEY` | `YOUR_KLING_API_KEY` | مفتاح محرك التلبيس الافتراضي Kling Kolors VTON. |

---

### د) مفاتيح التجارة والمدفوعات وسياسات الخصوصية (Commerce & Privacy)
| اسم المتغير (Key) | القيمة (Value) | الشرح |
|---|---|---|
| `MARKET` | `EG` | كود السوق الافتراضي (مصر: الجنيه المصري، أو `AE` للإمارات، `SA` للسعودية). |
| `FULFILL_PACE` | `demo` | وضع محاكاة التوصيل والاستلام من البوتيك (BOPIS 2h SLA). |
| `BNPL_DEFAULT_PROVIDER` | `tabby` | بوابة التقسيط الافتراضية بدون فوائد (Tabby / Tamara). |
| `PAYMENT_DEFAULT_PROVIDER` | `mock` | بوابة الدفع الافتراضية (بطاقات، محافظ إلكترونية، إنستاباي، كاش). |
| `POLICY_VERSION` | `3` | إصدار سياسة الخصوصية وحماية بيانات المستخدمين. |
| `TRYON_ANONYMOUS_EXPIRY_HOURS` | `24` | مدة حذف صور غرف القياس المؤقتة تلقائياً (24 ساعة). |
| `DUPLICATE_ALERT_SIMILARITY_THRESHOLD` | `0.82` | نسبة التشابه لتحذير العميل من شراء قطعة يمتلك مثلها في خزانته (82%). |
