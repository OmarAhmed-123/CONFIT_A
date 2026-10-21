# Uploading your clothing catalogue to CONFIT — brand owner guide

# دليل صاحب العلامة التجارية: رفع كتالوج المنتجات إلى CONFIT

> Two audiences, one file: English first, العربية afterwards.
> Everything here is enforced by the importer — if a rule below is not followed,
> the preview will show you exactly which row and which column to fix **before**
> anything is saved.

---

## English

### 1. Before you start

You need:

* a brand account on CONFIT (the upload page is **Catalog & SKU Management →
  Import Products from CSV**);
* one photo URL per product, publicly reachable over HTTPS, from
  `images.unsplash.com` / `images.pexels.com` (licensed stock) **or** your own
  hosting if your operator has enabled first-party images;
* prices in **USD** — that is the currency CONFIT stores prices in. The
  storefront shows them in EGP at the current rate. A row priced in any other
  currency is refused, because a price stored in one currency and displayed in
  another would show you one number and charge your customer a different one;
* the category of each item, chosen from exactly these six:
  `outerwear`, `tops`, `bottoms`, `dresses`, `footwear`, `accessories`.

You do **not** need, and must never include: your brand name, your email, your
password, an API token. CONFIT knows who you are from your login. A file that
contains credentials is rejected by policy — and never store credentials in a
spreadsheet that leaves your machine.

### 2. Get the template

Click **Download template**. That file is produced by the same code that
validates your upload, so it always matches the current rules. Edit it; do not
retype the header by hand.

### 3. One row = one variant

A shirt in three sizes is **three rows** with the **same product name** and three
different SKUs. CONFIT groups rows by `product_name`, so:

* the same `product_name` → one product, many sizes/colours;
* a different `product_name` → a different product.

Give every row a unique `sku` (3–100 letters, digits, `-` or `_`). If you leave it
blank, CONFIT derives a stable code from brand + name + size + colour — but an
explicit SKU is what your warehouse and your accountant will recognise.

### 4. Fill in the Arabic columns

`title_ar` and `description_ar` are not decoration: the storefront is
Arabic-first for a large part of its audience. If you leave them empty the
product still imports, and the Arabic pages show the English text **and tell you
so** in the preview. English text is never silently written into an Arabic column.

### 5. Images

The photo must be the garment you are selling. CONFIT downloads it, derives five
crops (portrait, square, landscape, wide, master) in two formats, stores them and
serves them from its own domain. If the image cannot be downloaded or decoded,
**the row is refused** rather than published with a broken picture.

### 6. Review the preview, then confirm

The preview shows, per row: valid or the exact error, and whether the row will
**create** a new product or **update** an existing one. It writes nothing.

* **Errors** — that row will not be imported. Fix and re-upload; accepted rows are
  not affected.
* **Warnings** — the row will import, but something will be visible to shoppers:
  stock 0 (CONFIT hides unpurchasable products), missing Arabic copy, gender
  inferred from the name.
* **Blocked** — nothing can be imported yet (for example, image storage is not
  configured). Fix the cause; do not retry blindly.

### 7. After the import

Re-uploading the same file is safe: rows update in place, nothing is duplicated,
and images are not re-processed when the photo has not changed. That makes the
CSV a stock sheet you can keep editing.

Every import is recorded in **Recent Import Jobs** with its accepted/rejected
counts and a downloadable error report.

### 8. If something fails

Download the **error report** — it lists the row number, the column, the value
you supplied and the corrective action. A real example of each:

| Message | What to do |
| --- | --- |
| `category_slug: Category "shirts" not found` | use one of the six slugs above |
| `compare_at_price must be greater than base_price` | a "was" price that is not higher is not a discount; clear it or raise it |
| `This image host is not an approved stock source` | use Unsplash/Pexels, or ask your operator to enable your own images |
| `Prices are stored in USD … this row declares EGP` | convert the price to USD |
| `SKU already belongs to product "…"` | a SKU cannot be moved between products; use a new one |

---

## العربية

### ١. قبل أن تبدأ

تحتاج إلى:

* حساب علامة تجارية على CONFIT (صفحة الرفع: **إدارة الكتالوج ورموز SKU ←
  استيراد المنتجات من ملف CSV**)؛
* رابط صورة واحد لكل منتج، متاح للعامة عبر HTTPS، من
  `images.unsplash.com` أو `images.pexels.com` (صور مرخّصة)، أو من استضافتك
  الخاصة إذا فعّل المشغّل الصور الخاصة بك؛
* الأسعار بالدولار الأمريكي (**USD**) — وهي العملة التي يحفظ بها CONFIT
  الأسعار، وتعرضها الواجهة بالجنيه المصري بسعر الصرف الحالي. أي سطر بعملة أخرى
  يُرفض، لأن حفظ السعر بعملة وعرضه بعملة أخرى يعني أن ترى رقمًا وتُحصّل من
  عميلك رقمًا مختلفًا؛
* تصنيف كل قطعة، من هذه الستة فقط:
  `outerwear`، `tops`، `bottoms`، `dresses`، `footwear`، `accessories`.

لا تحتاج — ويُمنع تمامًا — أن تكتب: اسم علامتك، بريدك، كلمة المرور، أو أي رمز
دخول. CONFIT يعرف هويتك من تسجيل الدخول. ولا تحفظ بيانات الدخول في أي جدول
بيانات يخرج من جهازك.

### ٢. نزّل القالب

اضغط **تنزيل القالب**. يُنتَج هذا الملف من الكود نفسه الذي يتحقق من رفعك، لذا
يطابق القواعد الحالية دائمًا. عدّل عليه، ولا تُعِد كتابة صف العناوين يدويًا.

### ٣. كل سطر = متغيّر واحد

قميص بثلاثة مقاسات = **ثلاثة أسطر** بنفس اسم المنتج وبثلاثة رموز SKU مختلفة.
يجمع CONFIT الأسطر حسب `product_name`، أي:

* نفس `product_name` ← منتج واحد بعدة مقاسات/ألوان؛
* اسم مختلف ← منتج مختلف.

اجعل لكل سطر رمز `sku` فريدًا (٣–١٠٠ حرف أو رقم أو `-` أو `_`). إذا تركته
فارغًا، يستنتج CONFIT رمزًا ثابتًا من العلامة والاسم والمقاس واللون — لكن الرمز
الصريح هو ما سيعرفه مخزنك ومحاسبك.

### ٤. املأ الأعمدة العربية

`title_ar` و`description_ar` ليستا زينة: الواجهة عربية أولًا لشريحة كبيرة من
الجمهور. إذا تركتهما فارغين فسيُستورد المنتج، وستعرض الصفحات العربية النص
الإنجليزي **وتخبرك بذلك** في المعاينة. لا يُكتب نص إنجليزي داخل عمود عربي دون
إشعار.

### ٥. الصور

يجب أن تكون الصورة للقطعة التي تبيعها. ينزّلها CONFIT، ويشتق منها خمس قصّات
(طولية، مربعة، أفقية، عريضة، رئيسية) بصيغتين، ويخزّنها ويقدّمها من نطاقه. إذا
تعذّر تنزيل الصورة أو قراءتها، **يُرفض السطر** بدلًا من نشره بصورة مكسورة.

### ٦. راجع المعاينة ثم أكّد

تعرض المعاينة لكل سطر: صحيح أو الخطأ المحدد، وما إذا كان السطر سينشئ منتجًا
جديدًا أم سيحدّث منتجًا قائمًا. المعاينة لا تكتب شيئًا.

* **أخطاء** — لن يُستورد هذا السطر. صحّحه وأعد الرفع؛ الأسطر المقبولة لا تتأثر.
* **تحذيرات** — سيُستورد السطر، لكن هناك ما سيراه المتسوق: مخزون صفر (يخفي
  CONFIT المنتجات غير القابلة للشراء)، أو غياب النص العربي، أو استنتاج الجنس.
* **محظور** — لا يمكن استيراد أي شيء الآن (مثلًا تخزين الصور غير مُهيّأ).
  عالِج السبب، ولا تُعِد المحاولة دون تغيير.

### ٧. بعد الاستيراد

إعادة رفع الملف نفسه آمنة: تُحدَّث الأسطر في مكانها، ولا تتكرر المنتجات، ولا
تُعاد معالجة الصور إذا لم تتغير. أي أن ملف CSV يمكن أن يكون ورقة مخزون تحرّرها
باستمرار.

كل عملية استيراد تُسجَّل في **مهام الاستيراد الأخيرة** بعدد المقبول والمرفوض، مع
تقرير أخطاء قابل للتنزيل.

### ٨. إذا فشل شيء

نزّل **تقرير الأخطاء**: يذكر رقم السطر، والعمود، والقيمة التي أدخلتها، والإجراء
التصحيحي.
