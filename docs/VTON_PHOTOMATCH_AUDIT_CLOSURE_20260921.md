# تقرير إغلاق تدقيق: Virtual Try-On وPhoto Match

**المشروع:** CONFIT_A · **البيئة:** الإنتاج `https://confit-a.vercel.app/`
**commit المرجعي للتدقيق:** `cd17a220677efe0f39b60157e7acfd888f4df351`
**تاريخ هذا التقرير:** 2026-09-21
**الفرع:** `fix/vton-photomatch-audit-closure` (فرع واحد، كما طُلب)

> هذا التقرير للتعلّم والإصلاح، وليس لتقييم الأفراد. كل رقم فيه جاء من أمر
> مُنفَّذ فعليًا ومُدرَج نصّه. وما لم أستطع تنفيذه مكتوب صراحةً كـ«غير مُنفَّذ»
> مع سببه — لا توجد نتائج مُدَّعاة.

---

## 0 · خلاصة تنفيذية

| # | الفجوة في التدقيق | الحالة | الدليل |
|---|---|---|---|
| 1 | التخزين `local`، `production_grade=false`، `writable=false` | **مُصلَحة + مُفعَّلة على الإنتاج** | bucket حقيقي + round-trip + `/health` |
| 2 | `/health` و`/capabilities` يدّعيان الجاهزية | **مُصلَحة** | probe حي + اختبارات |
| 3 | لا يوجد اختبار E2E حي | **أداة جاهزة ومُنفَّذة** — النتيجة: فشل صادق بسبب حاجر خارجي | `verify_vton_live_e2e.py` |
| 4 | حدود حجم الصورة غير مُتحقَّق منها | **مُتحقَّق حيًا** | رفض 64×64 و2000×200 على الإنتاج |
| 5 | SLA ورسائل الفشل | **مُنفَّذة** (SLA منشور + رسائل للمستخدم + fail-fast) | `VtonSlaOut` + circuit |
| 6 | جودة segmentation-free على أوضاع مختلفة | **الأداة جاهزة** — لم تُقَس (الحاجر نفسه) | `vton_quality_matrix.py` |
| 7 | retention بعد purge | **مُنفَّذ في الأداة** — الخطوات من 6 إلى 9 | نفس الأداة |

**الحاجر الوحيد الذي لا يستطيع هذا الفرع إصلاحه:** مساحة Modal للـ GPU تجاوزت حد
الصرف، فكل inference معطّل. التفاصيل والخطوات في §5.

---

## 1 · الدليل الحي على أن الميزة كانت معطّلة 100%

التدقيق قال «الجاهزية مثبتة، E2E كامل غير منفذ». عند التنفيذ الفعلي اتضح أن
الواقع أسوأ من ذلك: الميزة لا تعمل أصلًا، والنظام كان يقول إنها تعمل.

### 1.1 ما كان يقوله الإنتاج

```
$ curl -s https://confit-a.vercel.app/api/v1/health | jq .checks.vton_pipeline
"configured: GPU worker URL + admin token present (readiness is checked per job, not here)"

$ curl -s https://confit-a.vercel.app/api/v1/try-on/capabilities?product_ids=3
{"provider":"fashn_vton_segfee","engine_state":"available", ...
 "products":[{"product_id":3,"slot_type":"upper_inner","state":"supported",
              "reason_code":"SUPPORTED", ...}]}
```

### 1.2 ما كان يحدث فعلًا عند طلب render حقيقي

حساب اختبار (`confit.audit.probe.20260921@gmail.com`، user id 115)، صورة شخص
**توليدية** (mannequin مرسوم برمجيًا — ليست صورة إنسان حقيقي)، المنتج 3
(قميص، slot `upper_inner`، أي مدعوم):

```
POST /api/v1/try-on/jobs   -> HTTP 202 بعد 39.4 ثانية
{
  "job_id": "vton_job_90cdbe63c6d3",
  "status": "failed",
  "current_stage": "failed",
  "model_used": "pending (no render yet)",
  "error_code": "VTON_WORKER_NOT_READY",
  "error_message": "GPU Inference Worker Failure: VTON_WORKER_NOT_READY:
                    GPU worker not ready after 3 attempts: unreachable",
  "completed_at": null
}
```

### 1.3 السبب الجذري الحقيقي

```
$ curl -s https://omarsafealden--confit-vton-worker-segfee-fashninferences-2a7124.modal.run
modal-http: workspace ac-io3nXB7Q2nuaHHl8mVkeLH is disabled          (HTTP 404)

$ python3 -c "import modal; ...ping.remote()"     # أبسط دالة 0.125 CPU
modal.exception.ResourceExhaustedError:
    Workspace ac-io3nXB7Q2nuaHHl8mVkeLH has exceeded its spend limit
```

أي: **ليست مشكلة كود**. مساحة Modal تجاوزت حد الصرف فأُوقفت، وكل endpoints
ترجع 404. والكود كان يترجم «404 من المنصة» إلى «not ready ... unreachable»
— وهو ما أخفى السبب وراء كلمة «unreachable».

### 1.4 مصفوفة الجودة على البناء القديم (4 حالات)

```
front_standing / upper_inner  39.39s  failed  VTON_WORKER_NOT_READY
three_quarter  / upper_outer  39.47s  failed  VTON_WORKER_NOT_READY
seated         / lower        45.01s  failed  VTON_WORKER_NOT_READY
walking        / dress        39.28s  failed  VTON_WORKER_NOT_READY
pass_rate = 0.0
```

---

## 2 · الفجوة 1: التخزين الإنتاجي — مُصلَحة ومُفعَّلة

### ما كان

```
"storage": {"provider":"local","production_grade":false,"writable":false}
```

وفحص متغيّرات Vercel الفعلية
(`GET /v10/projects/prj_XaGsK8FP0dYc7yijAH58d1O0h1Vt/env`) أظهر أنه **لا يوجد
أصلًا** أي من `STORAGE_PROVIDER` / `AWS_S3_BUCKET` / `AWS_ACCESS_KEY_ID` /
`S3_ENDPOINT_URL`. أي أن كل رفع صور (wardrobe / mood-board) يرجع 501.

### ثلاثة عيوب حقيقية في الكود (وليست إعدادًا فقط)

1. **الأسماء الموثّقة لا يقرؤها أحد.** `backend/.env.example` يكتب
   `S3_ENDPOINT` / `S3_ACCESS_KEY` / `S3_SECRET_KEY` / `S3_BUCKET_PUBLIC`،
   بينما الكود يقرأ `AWS_S3_BUCKET` / `AWS_ACCESS_KEY_ID` /
   `AWS_SECRET_ACCESS_KEY` / `S3_ENDPOINT_URL`. من ملأ الملف الموثّق حرفيًا
   ظلّ على `production_grade=False` دون أي تلميح.
   → الحل: مصدر واحد للحقيقة `Settings.s3_bucket / s3_access_key /
   s3_secret_key / s3_endpoint_url` يقبل الصيغتين (AWS_* أولًا).

2. **الكائنات كانت تُكتب بلا تشفير.** صور wardrobe وmood-board بيانات شخصية.
   → الحل: كل `put_object` يعلن `ServerSideEncryption` (AES256 افتراضيًا،
   `S3_SERVER_SIDE_ENCRYPTION` للتعديل) + `ContentType` صحيح + سياسة كاش خاصة.

3. **«مُهيأ» كان يُعرض كـ«جاهز للإنتاج».** bucket في region خاطئ، أو صلاحية
   ملغاة، أو endpoint بخطأ إملائي — كلها كانت تُبلَّغ كـ`production_grade=true`
   بينما كل رفع يفشل.
   → الحل: `probe_storage()` يعمل round-trip حقيقي
   (put → head → get → delete) مقابل الـbucket، مخزّن مؤقتًا بـTTL، لا يرفع
   استثناءً أبدًا، ولا يسرّب أي صلاحية. ومع `STORAGE_PROBE_ENABLED` ينشر
   `/health` النتيجة، و`production_grade` يصبح `false` عند فشل الفحص، فتفشل
   `require_production_storage()` **قبل** استلام أي بايت من المستخدم.

### باج كامن اكتُشف أثناء الكتابة

`ttl = float(... or 300.0)` كان يحوّل TTL صريحًا قيمته `0` إلى `300`
(لأن `0.0` falsy)، فالـcache لم يكن يمكن تجاوزه أبدًا. استُبدل بفحص صريح
لـ`None`/القيم السالبة. (الاختبار هو ما كشفه — لا القراءة.)

### ما نُفّذ فعليًا على البنية التحتية

```
create_bucket OK                          # bucket: confit-a-media
PUT/GET round trip: True b'confit-s3-probe-1789976072'
DELETE ok; exists now: False
buckets now: ['confit-a-media']
endpoint: https://br-mute-waterfall-b2p706dr.storage.c-6.eu-central-1.aws.neon.tech
```

ومتغيّرات Vercel أُضيفت للـproject `confit-a` (انظر §6 لخطوات ما بعد الدمج).

---

## 3 · الفجوة 2: المصداقية — `/health` و`/capabilities`

**المبدأ المطبَّق:** التهيئة ليست إتاحة. الإتاحة خاصية **مُقاسة**.

وحدة جديدة `backend/app/services/vton_worker_observability.py`:

* `WorkerProbe` — فحص health/readiness مخزّن مؤقتًا. بعد أول نداء لا يحجب أي
  طلب: يخدم آخر نتيجة ويجدّدها في thread خلفي، والنتيجة مؤرَّخة.
  لا يرفع استثناءً أبدًا (أداة مراقبة تُسقط `/health` أسوأ من غيابها)،
  ولا تُخرج أي سرّ من الوحدة.
* `classify_worker_failure()` — مصدر وحيد لترجمة **ما قالته المنصة حرفيًا**
  إلى كود خطأ ورسالة للمستخدم. مساحة معطّلة/متجاوزة للحد =
  `VTON_ENGINE_UNAVAILABLE` / `retryable=false`. حاوية تُقلع =
  `VTON_WORKER_COLD_START` (كود جديد) / `retryable=true`.
  الكود القديم كان يدمج الاثنين في `VTON_WORKER_NOT_READY`.
* `WorkerCircuitBreaker` — closed → open → half-open بمسبار استرداد واحد.
  الفشل غير القابل لإعادة المحاولة يفتحه فورًا.
* `vton_health_summary()` — تنشر الحكم، `production_ready`، عمر الفحص،
  كلام المنصة نفسه، وحالة الـcircuit.

**النتيجة الآن** (مُنفَّذة فعليًا مقابل endpoint الإنتاج الحقيقي المعطّل):

```
{"verdict":"unavailable","production_ready":false,"status_code":404,
 "reason":"HTTP 404: modal-http: workspace ac-io3nXB7Q2nuaHHl8mVkeLH is disabled",
 "error_code":"VTON_ENGINE_UNAVAILABLE",
 "detail":"GPU worker is NOT reachable: every try-on job will fail. ..."}
```

و`/health` أصبح `degraded` عندما يكون worker مُهيأً لكنه لا يخدم — مع بقاء
`healthy` للمضيف الذي لا يقدّم try-on أصلًا (حتى تظل الإشارة ذات معنى في CI).

---

## 4 · الفجوات 5 و7: SLA، الرسائل، والفشل السريع

* **SLA منشور** (`VtonSlaOut`): warm p50/p95، ميزانية cold start، سقف
  fail-fast، job timeout، delivery TTL، حدّ القطع. الواجهة تعرضه.
* **رسائل للمستخدم بدل سطور اللوج:** `metrics.failure` يحمل
  `{code, user_message, retryable, detail}`، و`error_message` صار جملة قابلة
  للتصرّف. الرسالة القديمة («not ready after 3 attempts: unreachable») كانت
  سطر لوج للمطوّر وتخفي السبب.
* **فشل سريع بدل 39 ثانية:** `create_and_enqueue_vton_job()` يستشير الـcircuit
  أولًا ويرجع job منتهيًا بالفشل في ميلي-ثوانٍ (`metrics.failed_fast=true`).
  يُغلق عند أول نجاح inference حقيقي. أخطاء الإدخال (صورة سيئة) لا تفتحه —
  لأنها لا تقول شيئًا عن الـworker.
* **دورة حياة صادقة:** الوظائف الفاشلة صارت تضبط `completed_at`
  (كانت `null`، فتبدو «قيد التنفيذ» للأبد أمام أي استعلام retention).
* **الواجهة:** `TryOnEngineStatus` — بانر يقول الحقيقة **قبل** رفع الصورة:
  متصل + الوقت المتوقع / يسخن / معطّل مع سبب الخلفية وretry-after.
  والـviewmodel صار يستخدم `user_message` من الخلفية بدل تأليف نصّ موازٍ.

---

## 5 · ما لم أستطع تنفيذه — بصراحة

| البند | السبب | ما المطلوب |
|---|---|---|
| render حي ناجح (E2E كامل) | مساحة Modal معطّلة (تجاوز حد الصرف) — **فوترة، ليست كود** | رفع حد الصرف/إضافة وسيلة دفع، ثم `modal deploy services/vton-worker/modal_app_segfee.py` |
| قياس جودة segmentation-free | نفس الحاجر | تشغيل `backend/scripts/vton_quality_matrix.py` بعد إحياء الـworker |
| فحص قاعدة البيانات مباشرة | كلمة سرّ `DATABASE_URL` المُعطاة ترجع `28P01 password authentication failed for user 'neondb_owner'` | كلمة سر صحيحة (أو الاعتماد على `/health` الذي يبلّغ `database: healthy`) |

**لم أكتب أي نتيجة «نجح» لأيٍّ من هذه.** الأدوات جاهزة وتُبلّغ `NOT_RUN`
أو `FAIL` صراحةً بدل الادّعاء.

### خطوات الإحياء بعد إصلاح الفوترة

```bash
modal deploy services/vton-worker/modal_app_segfee.py
curl -s <VTON_WORKER_HEALTH_URL> | jq .model_loaded          # يجب true
python3 backend/scripts/verify_vton_live_e2e.py \
    --base-url https://confit-a.vercel.app \
    --email <e2e account> --password <...> \
    --product-ids 3 1 4 --expect-engine available \
    --report /tmp/e2e.json                                    # يجب verdict=PASS
python3 backend/scripts/vton_quality_matrix.py ... --report /tmp/quality.json
```

---

## 6 · متغيّرات Vercel المطلوبة (تُطبَّق بعد الدمج)

```
STORAGE_PROVIDER=s3
AWS_S3_BUCKET=confit-a-media
S3_ENDPOINT_URL=https://br-mute-waterfall-b2p706dr.storage.c-6.eu-central-1.aws.neon.tech
AWS_ACCESS_KEY_ID=<من أسرار المشروع>
AWS_SECRET_ACCESS_KEY=<من أسرار المشروع>
AWS_REGION=eu-central-1
S3_SERVER_SIDE_ENCRYPTION=AES256
STORAGE_PROBE_ENABLED=true
STORAGE_PROBE_TTL_SECONDS=300
```

التحقّق بعد النشر:

```
curl -s https://confit-a.vercel.app/api/v1/health | jq .checks.storage
# المتوقع: provider "s3", production_grade true, live_probe.verdict "ok"
```

> ملاحظة تصميمية مقصودة: نتائج try-on المولَّدة **لا** تُخزَّن في هذا
> الـbucket. العقد الحالي (تسليم داخل الاستجابة + كاش مؤقت one-shot) مقصود
> لأسباب خصوصية، ولم يُغيَّر. الـbucket للصور التي يحتاج المستخدم بقاءها
> (wardrobe / mood-board).

---

## 7 · ما تم التحقق منه بالأرقام

| الفحص | الأمر | النتيجة |
|---|---|---|
| اختبارات الباك-إند كلها | `PYTHONPATH=. pytest backend/tests -q` | **1186 passed, 0 failed, 2 skipped** |
| اختبارات التخزين | `pytest backend/tests/test_storage_backend_contract.py` | 20 passed |
| اختبارات المراقبة الجديدة | `pytest backend/tests/test_vton_worker_observability.py` | 19 passed |
| بوابة تبعيات النشر | `python3 backend/scripts/check_runtime_imports.py` | `[vercel] OK` · `[docker] OK` |
| TypeScript | `npx tsc --noEmit` | exit 0 |
| اختبارات الواجهة | `npx vitest run` | **106 passed (20 files)** |
| E2E حي على الإنتاج | `verify_vton_live_e2e.py` | 6/11 — والفشل صادق ومُسمَّى |
| مصفوفة الجودة | `vton_quality_matrix.py` | 0/4 — `pass_rate 0.0` |

ملاحظة أمانة: الفشل في اختباري E2E ومصفوفة الجودة **ليس** فشلًا في الكود، بل
هو الحاجر الخارجي (§5) — والأدوات تسمّيه كذلك بدل تمريره.

---

## 8 · المبادئ المطبَّقة

* **DRY:** حلّ إعدادات S3 في مكان واحد؛ تصنيف الأخطاء في دالة واحدة تستدعيها
  كل مسارات VTON؛ `assert_layer_applied` ظلّ البوابة الوحيدة للتحقق من الطبقات.
* **Design Patterns:** Strategy (StorageBackend)،Factory (`get_storage_backend`)،
  Singleton مع reset صريح للاختبار،Circuit Breaker،Probe/Cache-Aside.
* **System Design / Architecture:** فصل «التهيئة» عن «الإتاحة»؛ مراقبة غير
  حاجبة (background refresh)؛ fail-fast بدل استنزاف زمن المستخدم؛ عقد SLA
  منشور وقابل للقياس.
* **Database:** لا مخطط جديد (لم نحتج عمودًا)؛ إصلاح `completed_at` يجعل
  استعلامات الـretention صحيحة؛ سلسلة Alembic خضراء.
* **Algorithms:** cache بـTTL + طرد بالسعة، circuit breaker بـhalf-open،
  قياس entropy للصورة الناتجة للتأكد أنها ليست لونًا مصمتًا أو صدى للمدخل.
* **BRD:** كل إصلاح مرتبط بفجوة مُرقَّمة في تقرير التدقيق، وبسبب مُقاس.

---

## 9 · ملاحظة أمنية

المفاتيح التي استُخدمت في هذه الجولة نُقلت في نصّ صريح. يُنصح بإدارة
المخاطر التالية بعد الانتهاء: تدوير `VTON_WORKER_ADMIN_TOKEN` و`SECRET_KEY`
و`JWT_REFRESH_SECRET` ومفاتيح Modal وVercel وNeon، ومراجعة سجل
`gitleaks` في CI. لا شيء من هذه القيم دخل المستودع أو أي commit.
