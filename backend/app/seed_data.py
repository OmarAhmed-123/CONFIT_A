import json
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from backend.app.core.database import SessionLocal, Base, engine
from backend.app.core.security import get_password_hash, encrypt_sensitive_data
from backend.app.models.user import User, UserRole, BrandProfile, AuditLog
from backend.app.models.profile import UserStyleProfile
from backend.app.models.catalog import Category, Product, ProductSKU, StoreLocation, StoreInventory
from backend.app.models.stylist import StylistSession, StylistMessage, Outfit, OutfitItem
from backend.app.models.wardrobe import WardrobeItem, WardrobeGapAnalysis
from backend.app.models.commerce import Cart, CartItem, Order, OrderItem
from backend.app.models.brand_analytics import SponsoredPlacement, StyleHeatmapAggregate


def seed_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db: Session = SessionLocal()

    print("🌱 Seeding CONFIT Database with Comprehensive Multi-Brand Catalog...")

    # 1. Create Core Users
    consumer_user = User(
        email="shopper@confit.io",
        hashed_password=get_password_hash("Password123!"),
        full_name="Layla Al-Mansoor",
        role=UserRole.CONSUMER,
        phone="+971501234567",
        preferred_language="en",
        is_active=True,
        is_verified=True,
        mfa_enabled=False
    )
    db.add(consumer_user)

    admin_user = User(
        email="admin@confit.io",
        hashed_password=get_password_hash("Password123!"),
        full_name="CONFIT Super Admin",
        role=UserRole.ADMIN,
        phone="+971500000000",
        preferred_language="en",
        is_active=True,
        is_verified=True
    )
    db.add(admin_user)

    brand_users_defs = [
        ("brand@massimodutti.com", "Massimo Dutti Brand Manager"),
        ("brand@cos.com", "COS Brand Manager"),
        ("brand@reiss.com", "Reiss Brand Manager"),
        ("brand@arket.com", "Arket Brand Manager"),
    ]

    brand_user_objs = []
    for email, name in brand_users_defs:
        bu = User(
            email=email,
            hashed_password=get_password_hash("Password123!"),
            full_name=name,
            role=UserRole.BRAND_MANAGER,
            phone="+971509876543",
            preferred_language="en",
            is_active=True,
            is_verified=True
        )
        db.add(bu)
        brand_user_objs.append(bu)

    db.flush()

    # 2. User Style Profile (USP) for Consumer
    body_payload = {
        "height_cm": 178.0,
        "weight_kg": 72.0,
        "body_shape": "Athletic",
        "chest_cm": 98.0,
        "waist_cm": 82.0,
        "hip_cm": 96.0,
        "inseam_cm": 81.0
    }
    encrypted_body = encrypt_sensitive_data(json.dumps(body_payload))

    consumer_usp = UserStyleProfile(
        user_id=consumer_user.id,
        style_archetypes=json.dumps(["Smart Casual", "Quiet Luxury", "Modern Minimalist"]),
        preferred_colors=json.dumps(["Navy", "Beige", "Black", "Forest Green", "Ivory"]),
        avoided_colors=json.dumps(["Neon Orange", "Magenta"]),
        fashion_aesthetics=json.dumps(["Old Money", "Modern Tailored", "Relaxed Elegance"]),
        budget_monthly_min=250.0,
        budget_monthly_max=1500.0,
        budget_per_outfit_max=450.0,
        preferred_brands=json.dumps(["Massimo Dutti", "COS", "Reiss", "Arket"]),
        blacklisted_brands=json.dumps([]),
        occasion_weights=json.dumps({"work": 0.40, "casual": 0.35, "party": 0.15, "sports": 0.10}),
        size_tops="M",
        size_bottoms="32",
        size_shoes="42",
        fit_preference="regular",
        body_shape_tag="Athletic",
        encrypted_body_data=encrypted_body,
        onboarding_completed=True,
        privacy_consent_tryon_storage=True,
        privacy_consent_share_with_brands=False
    )
    db.add(consumer_usp)

    # 3. Brands
    brands_data = [
        {
            "user_id": brand_user_objs[0].id,
            "brand_name": "Massimo Dutti",
            "slug": "massimo-dutti",
            "logo_url": "https://images.unsplash.com/photo-1544441893-675973e31985?w=200&auto=format&fit=crop&q=80",
            "description": "Refined urban elegance crafted with premium Italian fabrics.",
            "description_ar": "أناقة حضرية راقية بأقمشة إيطالية فاخرة.",
            "commission_rate": 15,
            "return_rate_benchmark": 28,
            "current_return_rate": 8
        },
        {
            "user_id": brand_user_objs[1].id,
            "brand_name": "COS",
            "slug": "cos",
            "logo_url": "https://images.unsplash.com/photo-1490481651871-ab68de25d43d?w=200&auto=format&fit=crop&q=80",
            "description": "Contemporary, reinvented classics and wardrobe essentials.",
            "description_ar": "قطع كلاسيكية معاد ابتكارها وأساسيات خزانة معاصرة.",
            "commission_rate": 14,
            "return_rate_benchmark": 26,
            "current_return_rate": 9
        },
        {
            "user_id": brand_user_objs[2].id,
            "brand_name": "Reiss",
            "slug": "reiss",
            "logo_url": "https://images.unsplash.com/photo-1441984904996-e0b6ba687e04?w=200&auto=format&fit=crop&q=80",
            "description": "Modern British tailoring with an uncompromising eye on detail.",
            "description_ar": "تفصيل بريطاني عصري مع اهتمام استثنائي بالتفاصيل.",
            "commission_rate": 16,
            "return_rate_benchmark": 30,
            "current_return_rate": 7
        },
        {
            "user_id": brand_user_objs[3].id,
            "brand_name": "Arket",
            "slug": "arket",
            "logo_url": "https://images.unsplash.com/photo-1445205170230-053b83016050?w=200&auto=format&fit=crop&q=80",
            "description": "Nordic simplicity and sustainable, durable wardrobe foundations.",
            "description_ar": "بساطة اسكندنافية وقطع مستدامة تدوم طويلاً.",
            "commission_rate": 12,
            "return_rate_benchmark": 24,
            "current_return_rate": 10
        }
    ]

    brand_objs = []
    for b in brands_data:
        bp = BrandProfile(**b)
        db.add(bp)
        brand_objs.append(bp)
    db.flush()

    # 4. Categories
    categories_data = [
        {"name": "Outerwear", "name_ar": "الملابس الخارجية", "slug": "outerwear", "icon_name": "sparkle"},
        {"name": "Tops & Shirts", "name_ar": "القمصان والبلوزات", "slug": "tops", "icon_name": "hanger"},
        {"name": "Bottoms & Trousers", "name_ar": "البناطيل والتنانير", "slug": "bottoms", "icon_name": "hanger"},
        {"name": "Dresses", "name_ar": "الفساتين", "slug": "dresses", "icon_name": "sparkle"},
        {"name": "Footwear", "name_ar": "الأحذية", "slug": "footwear", "icon_name": "ruler"},
        {"name": "Accessories", "name_ar": "الإكسسوارات", "slug": "accessories", "icon_name": "sparkle"}
    ]

    category_objs = []
    for c in categories_data:
        cat = Category(**c)
        db.add(cat)
        category_objs.append(cat)
    db.flush()

    cat_outerwear = category_objs[0]
    cat_tops = category_objs[1]
    cat_bottoms = category_objs[2]
    cat_dresses = category_objs[3]
    cat_footwear = category_objs[4]
    cat_accessories = category_objs[5]

    brand_md = brand_objs[0]
    brand_cos = brand_objs[1]
    brand_reiss = brand_objs[2]
    brand_arket = brand_objs[3]

    # 5. Products & SKUs across all slots and styles
    products_seed = [
        # --- 1. Outerwear ---
        {
            "brand_id": brand_md.id,
            "category_id": cat_outerwear.id,
            "title": "Tailored Italian Wool Double-Breasted Blazer",
            "title_ar": "سترة بليزر صوف إيطالي بصدر مزدوج",
            "slug": "tailored-italian-wool-double-breasted-blazer",
            "description": "Exquisite structured tailoring crafted in 100% fine Italian virgin wool. Features notched lapels, horn buttons, and breathable cupro lining.",
            "description_ar": "قصة مفصلة متقنة مصنوعة من صوف فيرجن إيطالي 100٪. تتميز بياقة كلاسيكية وبطانة ناعمة تسمح بمرور الهواء.",
            "base_price": 289.0,
            "currency": "USD",
            "material": "100% Virgin Wool",
            "care_instructions": "Specialist Dry Clean Only",
            "style_tags": json.dumps(["smart_casual", "quiet_luxury", "formal", "tailored"]),
            "occasion_tags": json.dumps(["wedding", "formal", "work", "business", "dinner", "party"]),
            "color_family": "Navy Blue",
            "dominant_hex": "#1B1F3B",
            "thumbnail_url": "https://images.unsplash.com/photo-1594938298603-c8148c4dae35?w=700&auto=format&fit=crop&q=80",
            "images": json.dumps([
                "https://images.unsplash.com/photo-1594938298603-c8148c4dae35?w=700&auto=format&fit=crop&q=80",
                "https://images.unsplash.com/photo-1507679799987-c73779587ccf?w=700&auto=format&fit=crop&q=80"
            ]),
            "rating": 4.9,
            "style_compatibility_base": 96,
            "is_featured": True,
            "skus": [
                {"sku_code": "MD-BLZ-NVY-S", "size": "S", "color": "Navy Blue", "color_hex": "#1B1F3B", "stock_level": 12},
                {"sku_code": "MD-BLZ-NVY-M", "size": "M", "color": "Navy Blue", "color_hex": "#1B1F3B", "stock_level": 18},
                {"sku_code": "MD-BLZ-NVY-L", "size": "L", "color": "Navy Blue", "color_hex": "#1B1F3B", "stock_level": 15},
                {"sku_code": "MD-BLZ-NVY-XL", "size": "XL", "color": "Navy Blue", "color_hex": "#1B1F3B", "stock_level": 6}
            ]
        },
        {
            "brand_id": brand_reiss.id,
            "category_id": cat_outerwear.id,
            "title": "Tuxedo Peak Lapel Evening Dinner Jacket",
            "title_ar": "سترة توكسيدو سهرة بياقة ساتان مدببة",
            "slug": "tuxedo-peak-lapel-evening-dinner-jacket",
            "description": "Black-tie evening jacket with lustrous silk satin peak lapels and covered single button fastening.",
            "description_ar": "سترة سهرة فاخرة بياقة حريرية عريضة وتفصيل بريطاني متقن للمناسبات الكبرى وحفلات الزفاف.",
            "base_price": 395.0,
            "currency": "USD",
            "material": "100% Fine Wool & Silk Satin",
            "care_instructions": "Specialist Dry Clean Only",
            "style_tags": json.dumps(["formal", "black_tie", "quiet_luxury", "evening"]),
            "occasion_tags": json.dumps(["wedding", "formal", "gala", "party", "dinner"]),
            "color_family": "Midnight Black",
            "dominant_hex": "#0B0C10",
            "thumbnail_url": "https://images.unsplash.com/photo-1507679799987-c73779587ccf?w=700&auto=format&fit=crop&q=80",
            "images": json.dumps(["https://images.unsplash.com/photo-1507679799987-c73779587ccf?w=700&auto=format&fit=crop&q=80"]),
            "rating": 4.9,
            "style_compatibility_base": 98,
            "is_featured": True,
            "skus": [
                {"sku_code": "REISS-TUX-BLK-38", "size": "38R", "color": "Midnight Black", "color_hex": "#0B0C10", "stock_level": 8},
                {"sku_code": "REISS-TUX-BLK-40", "size": "40R", "color": "Midnight Black", "color_hex": "#0B0C10", "stock_level": 14},
                {"sku_code": "REISS-TUX-BLK-42", "size": "42R", "color": "Midnight Black", "color_hex": "#0B0C10", "stock_level": 9}
            ]
        },
        {
            "brand_id": brand_cos.id,
            "category_id": cat_outerwear.id,
            "title": "Structured Double-Breasted Wool Overcoat",
            "title_ar": "معطف صوف بصدر مزدوج وتصميم عصري",
            "slug": "structured-double-breasted-wool-overcoat",
            "description": "Minimalist double-breasted overcoat in rich camel recycled wool with deep welt pockets.",
            "description_ar": "معطف أنيق من صوف الجمل الفاخر بقصة عصرية دافئة تناسب الإطلالات الرسمية والعملية.",
            "base_price": 350.0,
            "currency": "USD",
            "material": "80% Recycled Wool, 20% Polyamide",
            "care_instructions": "Dry Clean Only",
            "style_tags": json.dumps(["minimalist", "quiet_luxury", "smart_casual"]),
            "occasion_tags": json.dumps(["work", "business", "casual", "dinner"]),
            "color_family": "Camel Tan",
            "dominant_hex": "#B8860B",
            "thumbnail_url": "https://images.unsplash.com/photo-1539571696357-5a69c17a67c6?w=700&auto=format&fit=crop&q=80",
            "images": json.dumps(["https://images.unsplash.com/photo-1539571696357-5a69c17a67c6?w=700&auto=format&fit=crop&q=80"]),
            "rating": 4.8,
            "style_compatibility_base": 93,
            "is_featured": False,
            "skus": [
                {"sku_code": "COS-COT-CML-M", "size": "M", "color": "Camel Tan", "color_hex": "#B8860B", "stock_level": 10},
                {"sku_code": "COS-COT-CML-L", "size": "L", "color": "Camel Tan", "color_hex": "#B8860B", "stock_level": 8}
            ]
        },
        {
            "brand_id": brand_md.id,
            "category_id": cat_outerwear.id,
            "title": "Structured Linen Blend Summer Blazer",
            "title_ar": "سترة بليزر صيفية من الكتان الخفيف",
            "slug": "structured-linen-blend-summer-blazer",
            "description": "Unlined lightweight summer tailoring in airy Mediterranean linen and cotton blend.",
            "description_ar": "سترة كتان صيفية خفيفة بدون بطانة مثالية للمناسبات المفتوحة وحفلات الاستقبال.",
            "base_price": 260.0,
            "currency": "USD",
            "material": "65% Linen, 35% Cotton",
            "care_instructions": "Specialist Dry Clean",
            "style_tags": json.dumps(["smart_casual", "summer", "relaxed_elegance"]),
            "occasion_tags": json.dumps(["wedding", "party", "casual", "dinner"]),
            "color_family": "Sandstone Beige",
            "dominant_hex": "#D8C7B5",
            "thumbnail_url": "https://images.unsplash.com/photo-1548883354-7622d03aca27?w=700&auto=format&fit=crop&q=80",
            "images": json.dumps(["https://images.unsplash.com/photo-1548883354-7622d03aca27?w=700&auto=format&fit=crop&q=80"]),
            "rating": 4.7,
            "style_compatibility_base": 92,
            "is_featured": False,
            "skus": [
                {"sku_code": "MD-BLZ-SAN-M", "size": "M", "color": "Sandstone Beige", "color_hex": "#D8C7B5", "stock_level": 15},
                {"sku_code": "MD-BLZ-SAN-L", "size": "L", "color": "Sandstone Beige", "color_hex": "#D8C7B5", "stock_level": 11}
            ]
        },

        # --- 2. Tops & Shirts ---
        {
            "brand_id": brand_cos.id,
            "category_id": cat_tops.id,
            "title": "Relaxed Organic Poplin Oxford Shirt",
            "title_ar": "قميص أكسفورد من البوبلين العضوي بقصة مريحة",
            "slug": "relaxed-organic-poplin-oxford-shirt",
            "description": "Minimalist collared shirt in crisp organic poplin with subtle mother-of-pearl buttons. Pairs effortlessly under tailored jackets or solo.",
            "description_ar": "قميص ياقة كلاسيكي أنيق من البوبلين العضوي الناعم مع أزرار عرق اللؤلؤ.",
            "base_price": 95.0,
            "currency": "USD",
            "material": "100% Organic Cotton",
            "care_instructions": "Machine Wash 30°C Gentle",
            "style_tags": json.dumps(["minimalist", "smart_casual", "formal", "tailored"]),
            "occasion_tags": json.dumps(["wedding", "formal", "work", "business", "casual", "dinner"]),
            "color_family": "Optic White",
            "dominant_hex": "#FAF9F6",
            "thumbnail_url": "https://images.unsplash.com/photo-1602810318383-e386cc2a3ccf?w=700&auto=format&fit=crop&q=80",
            "images": json.dumps(["https://images.unsplash.com/photo-1602810318383-e386cc2a3ccf?w=700&auto=format&fit=crop&q=80"]),
            "rating": 4.8,
            "style_compatibility_base": 95,
            "is_featured": True,
            "skus": [
                {"sku_code": "COS-SHT-WHT-S", "size": "S", "color": "Optic White", "color_hex": "#FAF9F6", "stock_level": 25},
                {"sku_code": "COS-SHT-WHT-M", "size": "M", "color": "Optic White", "color_hex": "#FAF9F6", "stock_level": 30},
                {"sku_code": "COS-SHT-WHT-L", "size": "L", "color": "Optic White", "color_hex": "#FAF9F6", "stock_level": 20}
            ]
        },
        {
            "brand_id": brand_reiss.id,
            "category_id": cat_tops.id,
            "title": "Modern Slim-Fit Dress Shirt with French Cuffs",
            "title_ar": "قميص رسمي مفصل بأكمام فرنسية",
            "slug": "modern-slim-fit-dress-shirt-french-cuffs",
            "description": "Impeccable tailored formal shirt in two-fold Egyptian cotton with semi-cutaway collar and French cuffs.",
            "description_ar": "قميص سهرة رسمي فاخر من القطن المصري عالي الجودة مع أساور فرنسية.",
            "base_price": 135.0,
            "currency": "USD",
            "material": "100% Egyptian Cotton",
            "care_instructions": "Warm Iron Dry Clean Preferred",
            "style_tags": json.dumps(["formal", "black_tie", "quiet_luxury", "tailored"]),
            "occasion_tags": json.dumps(["wedding", "formal", "gala", "work", "business"]),
            "color_family": "Crisp White",
            "dominant_hex": "#FFFFFF",
            "thumbnail_url": "https://images.unsplash.com/photo-1596755094514-f87e34085b2c?w=700&auto=format&fit=crop&q=80",
            "images": json.dumps(["https://images.unsplash.com/photo-1596755094514-f87e34085b2c?w=700&auto=format&fit=crop&q=80"]),
            "rating": 4.9,
            "style_compatibility_base": 97,
            "is_featured": False,
            "skus": [
                {"sku_code": "REISS-SHT-WHT-15H", "size": "15.5 (M)", "color": "Crisp White", "color_hex": "#FFFFFF", "stock_level": 16},
                {"sku_code": "REISS-SHT-WHT-16", "size": "16 (L)", "color": "Crisp White", "color_hex": "#FFFFFF", "stock_level": 14}
            ]
        },
        {
            "brand_id": brand_md.id,
            "category_id": cat_tops.id,
            "title": "Pure Silk Collared Dress Blouse & Shirt",
            "title_ar": "قميص وبلوزة حرير خالص بياقة منسدلة",
            "slug": "pure-silk-collared-dress-shirt",
            "description": "Sublime 100% mulberry silk with gentle pearl sheen and fluid tailored silhouette.",
            "description_ar": "قميص حرير خالص ناعم الملمس يضفي لمسة فخامة وأناقة هادئة على الإطلالات الرسمية والمسائية.",
            "base_price": 160.0,
            "currency": "USD",
            "material": "100% Mulberry Silk",
            "care_instructions": "Specialist Dry Clean",
            "style_tags": json.dumps(["quiet_luxury", "formal", "evening"]),
            "occasion_tags": json.dumps(["wedding", "party", "dinner", "formal"]),
            "color_family": "Ivory Cream",
            "dominant_hex": "#F5F2EB",
            "thumbnail_url": "https://images.unsplash.com/photo-1589310243389-96a5483213a8?w=700&auto=format&fit=crop&q=80",
            "images": json.dumps(["https://images.unsplash.com/photo-1589310243389-96a5483213a8?w=700&auto=format&fit=crop&q=80"]),
            "rating": 4.9,
            "style_compatibility_base": 96,
            "is_featured": True,
            "skus": [
                {"sku_code": "MD-SHT-IVR-S", "size": "S", "color": "Ivory Cream", "color_hex": "#F5F2EB", "stock_level": 10},
                {"sku_code": "MD-SHT-IVR-M", "size": "M", "color": "Ivory Cream", "color_hex": "#F5F2EB", "stock_level": 14}
            ]
        },
        {
            "brand_id": brand_cos.id,
            "category_id": cat_tops.id,
            "title": "Cashmere Blend Funnel Neck Knit Sweater",
            "title_ar": "كنزة صوف كشمير بياقة قمعية أنيقة",
            "slug": "cashmere-blend-funnel-neck-sweater",
            "description": "Ultra-soft 70% merino wool and 30% cashmere yarn in a relaxed ribbed silhouette.",
            "description_ar": "كنزة شتوية فائقة النعومة من مزيج صوف الميرينو والكشمير الفاخر.",
            "base_price": 175.0,
            "currency": "USD",
            "material": "70% Merino Wool, 30% Cashmere",
            "care_instructions": "Hand Wash Cold Flat Dry",
            "style_tags": json.dumps(["minimalist", "quiet_luxury", "smart_casual"]),
            "occasion_tags": json.dumps(["casual", "work", "weekend", "dinner"]),
            "color_family": "Sage Green",
            "dominant_hex": "#2D4A3E",
            "thumbnail_url": "https://images.unsplash.com/photo-1576566588028-4147f3842f27?w=700&auto=format&fit=crop&q=80",
            "images": json.dumps(["https://images.unsplash.com/photo-1576566588028-4147f3842f27?w=700&auto=format&fit=crop&q=80"]),
            "rating": 4.9,
            "style_compatibility_base": 91,
            "is_featured": True,
            "skus": [
                {"sku_code": "COS-KNT-GRN-S", "size": "S", "color": "Sage Green", "color_hex": "#2D4A3E", "stock_level": 15},
                {"sku_code": "COS-KNT-GRN-M", "size": "M", "color": "Sage Green", "color_hex": "#2D4A3E", "stock_level": 20},
                {"sku_code": "COS-KNT-GRN-L", "size": "L", "color": "Sage Green", "color_hex": "#2D4A3E", "stock_level": 12}
            ]
        },
        {
            "brand_id": brand_arket.id,
            "category_id": cat_tops.id,
            "title": "Heavyweight Relaxed Linen Shirt",
            "title_ar": "قميص كتان نقي مريح وعالي الجودة",
            "slug": "heavyweight-relaxed-linen-shirt",
            "description": "Breathable 100% French linen garment-dyed in deep navy for relaxed warm-weather elegance.",
            "description_ar": "قميص كتان فرنسي طبيعي ومريح يوفر انتعاشاً وأناقة غير متكلفة في الطقس المعتدل.",
            "base_price": 110.0,
            "currency": "USD",
            "material": "100% French Linen",
            "care_instructions": "Machine Wash Warm",
            "style_tags": json.dumps(["relaxed_elegance", "smart_casual", "summer"]),
            "occasion_tags": json.dumps(["casual", "weekend", "dinner"]),
            "color_family": "Navy Blue",
            "dominant_hex": "#1B1F3B",
            "thumbnail_url": "https://images.unsplash.com/photo-1598033129183-c4f50c736f10?w=700&auto=format&fit=crop&q=80",
            "images": json.dumps(["https://images.unsplash.com/photo-1598033129183-c4f50c736f10?w=700&auto=format&fit=crop&q=80"]),
            "rating": 4.8,
            "style_compatibility_base": 92,
            "is_featured": False,
            "skus": [
                {"sku_code": "ARK-SHT-NVY-M", "size": "M", "color": "Navy Blue", "color_hex": "#1B1F3B", "stock_level": 18},
                {"sku_code": "ARK-SHT-NVY-L", "size": "L", "color": "Navy Blue", "color_hex": "#1B1F3B", "stock_level": 14}
            ]
        },

        # --- 3. Bottoms & Trousers ---
        {
            "brand_id": brand_md.id,
            "category_id": cat_bottoms.id,
            "title": "Matching Italian Wool Pleated Suit Trousers",
            "title_ar": "بنطال بدلة صوف إيطالي بكسرات متناسق",
            "slug": "matching-italian-wool-pleated-suit-trousers",
            "description": "Tailored trousers in fine Italian virgin wool with single front pleats and side waist tab adjusters.",
            "description_ar": "بنطال بدلة رسمي من الصوف الإيطالي الفاخر بتفصيل كلاسيكي وكسرات أمامية متناسقة تماماً مع السترة.",
            "base_price": 159.0,
            "currency": "USD",
            "material": "100% Virgin Wool",
            "care_instructions": "Dry Clean Only",
            "style_tags": json.dumps(["formal", "quiet_luxury", "smart_casual", "tailored"]),
            "occasion_tags": json.dumps(["wedding", "formal", "work", "business", "dinner"]),
            "color_family": "Navy Blue",
            "dominant_hex": "#1B1F3B",
            "thumbnail_url": "https://images.unsplash.com/photo-1506630448388-4e683c67ddb0?w=700&auto=format&fit=crop&q=80",
            "images": json.dumps(["https://images.unsplash.com/photo-1506630448388-4e683c67ddb0?w=700&auto=format&fit=crop&q=80"]),
            "rating": 4.9,
            "style_compatibility_base": 97,
            "is_featured": True,
            "skus": [
                {"sku_code": "MD-TR-NVY-30", "size": "30", "color": "Navy Blue", "color_hex": "#1B1F3B", "stock_level": 10},
                {"sku_code": "MD-TR-NVY-32", "size": "32", "color": "Navy Blue", "color_hex": "#1B1F3B", "stock_level": 20},
                {"sku_code": "MD-TR-NVY-34", "size": "34", "color": "Navy Blue", "color_hex": "#1B1F3B", "stock_level": 14}
            ]
        },
        {
            "brand_id": brand_md.id,
            "category_id": cat_bottoms.id,
            "title": "Pleated Tapered Crease Chino Trousers",
            "title_ar": "بنطال تشينو بكسرات وقصة مدببة أنيقة",
            "slug": "pleated-tapered-crease-chino-trousers",
            "description": "Modern tapered silhouette tailored with front double pleats and side tab adjusters. Clean drape in stretch cotton gabardine.",
            "description_ar": "قصة عصرية مدببة مع كسرات أمامية وأحزمة جانبية للتعديل من قماش قطني مرن.",
            "base_price": 145.0,
            "currency": "USD",
            "material": "98% Cotton, 2% Elastane",
            "care_instructions": "Machine Wash Cold",
            "style_tags": json.dumps(["smart_casual", "quiet_luxury", "minimalist"]),
            "occasion_tags": json.dumps(["work", "business", "casual", "dinner"]),
            "color_family": "Beige Sand",
            "dominant_hex": "#D8C7B5",
            "thumbnail_url": "https://images.unsplash.com/photo-1624378439575-d8705ad7ae80?w=700&auto=format&fit=crop&q=80",
            "images": json.dumps(["https://images.unsplash.com/photo-1624378439575-d8705ad7ae80?w=700&auto=format&fit=crop&q=80"]),
            "rating": 4.7,
            "style_compatibility_base": 92,
            "is_featured": True,
            "skus": [
                {"sku_code": "MD-TR-BGE-30", "size": "30", "color": "Beige Sand", "color_hex": "#D8C7B5", "stock_level": 14},
                {"sku_code": "MD-TR-BGE-32", "size": "32", "color": "Beige Sand", "color_hex": "#D8C7B5", "stock_level": 22},
                {"sku_code": "MD-TR-BGE-34", "size": "34", "color": "Beige Sand", "color_hex": "#D8C7B5", "stock_level": 16}
            ]
        },
        {
            "brand_id": brand_reiss.id,
            "category_id": cat_bottoms.id,
            "title": "Tailored Tuxedo Wool Trousers with Satin Side Stripe",
            "title_ar": "بنطال توكسيدو صوف بخط جانبي من الساتان",
            "slug": "tailored-tuxedo-wool-trousers-satin-stripe",
            "description": "Formal evening trousers cut from premium black barathea wool featuring side silk satin braids.",
            "description_ar": "بنطال سهرة رسمي أسود بشريط جانبي من الساتان الحريري للمناسبات الرسمية وحفلات الزفاف الفاخرة.",
            "base_price": 195.0,
            "currency": "USD",
            "material": "100% Wool with Silk Trim",
            "care_instructions": "Specialist Dry Clean Only",
            "style_tags": json.dumps(["formal", "black_tie", "quiet_luxury"]),
            "occasion_tags": json.dumps(["wedding", "formal", "gala", "party"]),
            "color_family": "Midnight Black",
            "dominant_hex": "#0B0C10",
            "thumbnail_url": "https://images.unsplash.com/photo-1479064555552-3ef4979f8908?w=700&auto=format&fit=crop&q=80",
            "images": json.dumps(["https://images.unsplash.com/photo-1479064555552-3ef4979f8908?w=700&auto=format&fit=crop&q=80"]),
            "rating": 4.9,
            "style_compatibility_base": 98,
            "is_featured": False,
            "skus": [
                {"sku_code": "REISS-TR-BLK-32", "size": "32", "color": "Midnight Black", "color_hex": "#0B0C10", "stock_level": 12},
                {"sku_code": "REISS-TR-BLK-34", "size": "34", "color": "Midnight Black", "color_hex": "#0B0C10", "stock_level": 8}
            ]
        },
        {
            "brand_id": brand_cos.id,
            "category_id": cat_bottoms.id,
            "title": "Wide-Leg Tailored Wool Trousers",
            "title_ar": "بنطال صوف مفصل بقصة واسعة معاصرة",
            "slug": "wide-leg-tailored-wool-trousers",
            "description": "Architectural high-rise wide-leg trousers in charcoal mélange responsibly sourced wool.",
            "description_ar": "بنطال صوف عصري بخصر مرتفع وقصة انسيابية واسعة باللون الرمادي الفحمي.",
            "base_price": 160.0,
            "currency": "USD",
            "material": "100% RWS Wool",
            "care_instructions": "Dry Clean Only",
            "style_tags": json.dumps(["minimalist", "smart_casual", "modern_tailored"]),
            "occasion_tags": json.dumps(["work", "business", "casual", "dinner"]),
            "color_family": "Charcoal Grey",
            "dominant_hex": "#373D43",
            "thumbnail_url": "https://images.unsplash.com/photo-1551854838-212c50b4c184?w=700&auto=format&fit=crop&q=80",
            "images": json.dumps(["https://images.unsplash.com/photo-1551854838-212c50b4c184?w=700&auto=format&fit=crop&q=80"]),
            "rating": 4.8,
            "style_compatibility_base": 94,
            "is_featured": False,
            "skus": [
                {"sku_code": "COS-TR-CHR-30", "size": "30", "color": "Charcoal Grey", "color_hex": "#373D43", "stock_level": 12},
                {"sku_code": "COS-TR-CHR-32", "size": "32", "color": "Charcoal Grey", "color_hex": "#373D43", "stock_level": 18}
            ]
        },
        {
            "brand_id": brand_arket.id,
            "category_id": cat_bottoms.id,
            "title": "Straight-Leg Washed Denim Trousers",
            "title_ar": "بنطال جينز كلاسيكي بقصة مستقيمة",
            "slug": "straight-leg-washed-denim-trousers",
            "description": "Classic mid-rise straight jeans in sturdy organic cotton denim with subtle vintage wash.",
            "description_ar": "بنطال دينم قطني مريح بقصة مستقيمة وأسلوب كلاسيكي دائم.",
            "base_price": 120.0,
            "currency": "USD",
            "material": "100% Organic Cotton Denim",
            "care_instructions": "Machine Wash Inside Out",
            "style_tags": json.dumps(["casual", "minimalist", "streetwear"]),
            "occasion_tags": json.dumps(["casual", "weekend"]),
            "color_family": "Classic Indigo",
            "dominant_hex": "#2B3A42",
            "thumbnail_url": "https://images.unsplash.com/photo-1542272604-780c96856592?w=700&auto=format&fit=crop&q=80",
            "images": json.dumps(["https://images.unsplash.com/photo-1542272604-780c96856592?w=700&auto=format&fit=crop&q=80"]),
            "rating": 4.7,
            "style_compatibility_base": 88,
            "is_featured": False,
            "skus": [
                {"sku_code": "ARK-JNS-IND-32", "size": "32", "color": "Classic Indigo", "color_hex": "#2B3A42", "stock_level": 20}
            ]
        },

        # --- 4. Dresses ---
        {
            "brand_id": brand_reiss.id,
            "category_id": cat_dresses.id,
            "title": "Silk Slip Column Maxi Dress with Drape Neckline",
            "title_ar": "فستان ماكسي حرير بتصميم عامودي وياقة منسدلة",
            "slug": "silk-slip-column-maxi-dress",
            "description": "Sensual fluid drape in heavyweight sandwashed mulberry silk. Elegantly contours the silhouette with an open back and delicate straps.",
            "description_ar": "فستان حرير التوت الفاخر بقصة انسيابية ساحرة وياقة منسدلة مناسب لحفلات الزفاف والسهرات.",
            "base_price": 340.0,
            "currency": "USD",
            "material": "100% Mulberry Silk",
            "care_instructions": "Dry Clean Only",
            "style_tags": json.dumps(["quiet_luxury", "evening", "formal"]),
            "occasion_tags": json.dumps(["wedding", "party", "gala", "dinner", "formal"]),
            "color_family": "Champagne Gold",
            "dominant_hex": "#C5A059",
            "thumbnail_url": "https://images.unsplash.com/photo-1595777457583-95e059d581b8?w=700&auto=format&fit=crop&q=80",
            "images": json.dumps(["https://images.unsplash.com/photo-1595777457583-95e059d581b8?w=700&auto=format&fit=crop&q=80"]),
            "rating": 4.9,
            "style_compatibility_base": 98,
            "is_featured": True,
            "skus": [
                {"sku_code": "REISS-DRS-GLD-S", "size": "S", "color": "Champagne Gold", "color_hex": "#C5A059", "stock_level": 8},
                {"sku_code": "REISS-DRS-GLD-M", "size": "M", "color": "Champagne Gold", "color_hex": "#C5A059", "stock_level": 12},
                {"sku_code": "REISS-DRS-GLD-L", "size": "L", "color": "Champagne Gold", "color_hex": "#C5A059", "stock_level": 5}
            ]
        },
        {
            "brand_id": brand_cos.id,
            "category_id": cat_dresses.id,
            "title": "Pleated Asymmetric Midnight Evening Dress",
            "title_ar": "فستان سهرة بكسرات وقصة غير متماثلة",
            "slug": "pleated-asymmetric-midnight-evening-dress",
            "description": "Striking architectural pleated dress with single shoulder drape and flowing movement.",
            "description_ar": "فستان سهرة مبتكر بكسرات دقيقة وقصة كتف واحد ساحرة.",
            "base_price": 280.0,
            "currency": "USD",
            "material": "100% Recycled Polyester Pleat",
            "care_instructions": "Specialist Care Gentle Cycle",
            "style_tags": json.dumps(["minimalist", "evening", "formal"]),
            "occasion_tags": json.dumps(["wedding", "party", "dinner", "gala"]),
            "color_family": "Midnight Navy",
            "dominant_hex": "#1B1F3B",
            "thumbnail_url": "https://images.unsplash.com/photo-1566174053879-31528523f8ae?w=700&auto=format&fit=crop&q=80",
            "images": json.dumps(["https://images.unsplash.com/photo-1566174053879-31528523f8ae?w=700&auto=format&fit=crop&q=80"]),
            "rating": 4.8,
            "style_compatibility_base": 95,
            "is_featured": False,
            "skus": [
                {"sku_code": "COS-DRS-NVY-S", "size": "S", "color": "Midnight Navy", "color_hex": "#1B1F3B", "stock_level": 10},
                {"sku_code": "COS-DRS-NVY-M", "size": "M", "color": "Midnight Navy", "color_hex": "#1B1F3B", "stock_level": 14}
            ]
        },

        # --- 5. Footwear ---
        {
            "brand_id": brand_md.id,
            "category_id": cat_footwear.id,
            "title": "Handcrafted Goodyear-Welted Leather Oxford Shoes",
            "title_ar": "حذاء أكسفورد جلد إيطالي بحياكة يدوية",
            "slug": "handcrafted-goodyear-welted-leather-oxfords",
            "description": "Essential formal black oxfords handcrafted in smooth full-grain calfskin leather with polished closed lacing.",
            "description_ar": "حذاء أكسفورد كلاسيكي أسود من جلد العجل الفاخر بحياكة غوديير المتينة للمناسبات الرسمية والبدلات.",
            "base_price": 240.0,
            "currency": "USD",
            "material": "100% Full-Grain Calfskin",
            "care_instructions": "Polish with Black Wax Cream",
            "style_tags": json.dumps(["formal", "black_tie", "quiet_luxury", "tailored"]),
            "occasion_tags": json.dumps(["wedding", "formal", "gala", "work", "business"]),
            "color_family": "Ebony Black",
            "dominant_hex": "#111111",
            "thumbnail_url": "https://images.unsplash.com/photo-1614252235316-8c857d38b5f4?w=700&auto=format&fit=crop&q=80",
            "images": json.dumps(["https://images.unsplash.com/photo-1614252235316-8c857d38b5f4?w=700&auto=format&fit=crop&q=80"]),
            "rating": 4.9,
            "style_compatibility_base": 98,
            "is_featured": True,
            "skus": [
                {"sku_code": "MD-OXF-BLK-41", "size": "41", "color": "Ebony Black", "color_hex": "#111111", "stock_level": 10},
                {"sku_code": "MD-OXF-BLK-42", "size": "42", "color": "Ebony Black", "color_hex": "#111111", "stock_level": 15},
                {"sku_code": "MD-OXF-BLK-43", "size": "43", "color": "Ebony Black", "color_hex": "#111111", "stock_level": 12},
                {"sku_code": "MD-OXF-BLK-44", "size": "44", "color": "Ebony Black", "color_hex": "#111111", "stock_level": 8}
            ]
        },
        {
            "brand_id": brand_arket.id,
            "category_id": cat_footwear.id,
            "title": "Minimalist Calfskin Penny Loafers",
            "title_ar": "حذاء لوفر بيني جلد عجل بتصميم بسيط",
            "slug": "minimalist-calfskin-penny-loafers",
            "description": "Handcrafted Goodyear-welted loafers made from smooth full-grain calf leather. Leather sole with rubber heel cap for all-day comfort.",
            "description_ar": "حذاء لوفر مصنوع يدوياً من جلد العجل الطبيعي الفاخر بنعل مريح.",
            "base_price": 220.0,
            "currency": "USD",
            "material": "100% Calf Leather",
            "care_instructions": "Condition with Leather Balm",
            "style_tags": json.dumps(["smart_casual", "quiet_luxury", "old_money"]),
            "occasion_tags": json.dumps(["work", "business", "dinner", "casual", "wedding"]),
            "color_family": "Ebony Black",
            "dominant_hex": "#111111",
            "thumbnail_url": "https://images.unsplash.com/photo-1533867617858-e7b97e060509?w=700&auto=format&fit=crop&q=80",
            "images": json.dumps(["https://images.unsplash.com/photo-1533867617858-e7b97e060509?w=700&auto=format&fit=crop&q=80"]),
            "rating": 4.8,
            "style_compatibility_base": 95,
            "is_featured": False,
            "skus": [
                {"sku_code": "ARK-LFR-BLK-41", "size": "41", "color": "Ebony Black", "color_hex": "#111111", "stock_level": 10},
                {"sku_code": "ARK-LFR-BLK-42", "size": "42", "color": "Ebony Black", "color_hex": "#111111", "stock_level": 14},
                {"sku_code": "ARK-LFR-BLK-43", "size": "43", "color": "Ebony Black", "color_hex": "#111111", "stock_level": 11}
            ]
        },
        {
            "brand_id": brand_reiss.id,
            "category_id": cat_footwear.id,
            "title": "Strappy Heeled Leather Sandals",
            "title_ar": "صندل بكعب عالي وسيور جلدية أنيقة",
            "slug": "strappy-heeled-leather-sandals",
            "description": "Sculpted stiletto heel sandals in metallic champagne leather with delicate ankle tie straps.",
            "description_ar": "صندل سهرة أنيق بكعب رفيع ولون شامبين ذهبي للمناسبات والفساتين الفاخرة.",
            "base_price": 250.0,
            "currency": "USD",
            "material": "100% Metallic Nappa Leather",
            "care_instructions": "Store in Dust Bag",
            "style_tags": json.dumps(["quiet_luxury", "evening", "formal"]),
            "occasion_tags": json.dumps(["wedding", "party", "gala", "dinner"]),
            "color_family": "Metallic Gold",
            "dominant_hex": "#C5A059",
            "thumbnail_url": "https://images.unsplash.com/photo-1543163521-1bf539c55dd2?w=700&auto=format&fit=crop&q=80",
            "images": json.dumps(["https://images.unsplash.com/photo-1543163521-1bf539c55dd2?w=700&auto=format&fit=crop&q=80"]),
            "rating": 4.9,
            "style_compatibility_base": 97,
            "is_featured": False,
            "skus": [
                {"sku_code": "REISS-SDL-GLD-38", "size": "38", "color": "Metallic Gold", "color_hex": "#C5A059", "stock_level": 9},
                {"sku_code": "REISS-SDL-GLD-39", "size": "39", "color": "Metallic Gold", "color_hex": "#C5A059", "stock_level": 11}
            ]
        },
        {
            "brand_id": brand_cos.id,
            "category_id": cat_footwear.id,
            "title": "Minimalist Leather Derby Shoes",
            "title_ar": "حذاء ديربي جلد بني بتصميم كلاسيكي",
            "slug": "minimalist-leather-derby-shoes",
            "description": "Refined round-toe derbies in espresso burnished calf leather with cushioned footbed.",
            "description_ar": "حذاء ديربي أنيق باللون البني الإسبريسو مناسب للبدلات وللإطلالات شبه الرسمية.",
            "base_price": 210.0,
            "currency": "USD",
            "material": "100% Burnished Calf Leather",
            "care_instructions": "Condition Regularly",
            "style_tags": json.dumps(["smart_casual", "tailored", "quiet_luxury"]),
            "occasion_tags": json.dumps(["work", "business", "dinner", "wedding"]),
            "color_family": "Espresso Brown",
            "dominant_hex": "#4A3525",
            "thumbnail_url": "https://images.unsplash.com/photo-1520639888713-7851133b1ed0?w=700&auto=format&fit=crop&q=80",
            "images": json.dumps(["https://images.unsplash.com/photo-1520639888713-7851133b1ed0?w=700&auto=format&fit=crop&q=80"]),
            "rating": 4.8,
            "style_compatibility_base": 94,
            "is_featured": False,
            "skus": [
                {"sku_code": "COS-DRB-BRN-42", "size": "42", "color": "Espresso Brown", "color_hex": "#4A3525", "stock_level": 12}
            ]
        },
        {
            "brand_id": brand_arket.id,
            "category_id": cat_footwear.id,
            "title": "Clean Minimalist Leather Low-Top Sneakers",
            "title_ar": "حذاء رياضي جلد أبيض كلاسيكي بسيط",
            "slug": "clean-minimalist-leather-low-top-sneakers",
            "description": "Premium white nappa leather low-top sneakers with stitched cupsole construction.",
            "description_ar": "حذاء سنيكرز أبيض ناصع من جلد النابا الطبيعي يناسب الإطلالات الكاجوال العصرية.",
            "base_price": 170.0,
            "currency": "USD",
            "material": "100% Nappa Leather",
            "care_instructions": "Wipe Clean with Damp Cloth",
            "style_tags": json.dumps(["smart_casual", "minimalist", "casual"]),
            "occasion_tags": json.dumps(["casual", "weekend"]),
            "color_family": "Chalk White",
            "dominant_hex": "#FAF9F6",
            "thumbnail_url": "https://images.unsplash.com/photo-1560769629-975ec94e6a86?w=700&auto=format&fit=crop&q=80",
            "images": json.dumps(["https://images.unsplash.com/photo-1560769629-975ec94e6a86?w=700&auto=format&fit=crop&q=80"]),
            "rating": 4.8,
            "style_compatibility_base": 91,
            "is_featured": False,
            "skus": [
                {"sku_code": "ARK-SNK-WHT-42", "size": "42", "color": "Chalk White", "color_hex": "#FAF9F6", "stock_level": 25}
            ]
        },

        # --- 6. Accessories ---
        {
            "brand_id": brand_md.id,
            "category_id": cat_accessories.id,
            "title": "100% Mulberry Silk Twill Tie",
            "title_ar": "ربطة عنق حرير التوت 100٪ باللون الأخضر الزمردي",
            "slug": "mulberry-silk-twill-tie-emerald",
            "description": "Luxurious 8cm silk twill necktie hand-stitched in Italy. Deep rich emerald green with subtle diagonal texture.",
            "description_ar": "ربطة عنق إيطالية فاخرة من حرير التوت الطبيعي باللون الأخضر الزمردي الراقي لإتمام البدلة الرسمية.",
            "base_price": 69.0,
            "currency": "USD",
            "material": "100% Mulberry Silk",
            "care_instructions": "Dry Clean Only",
            "style_tags": json.dumps(["formal", "wedding", "quiet_luxury", "tailored"]),
            "occasion_tags": json.dumps(["wedding", "formal", "work", "business"]),
            "color_family": "Emerald Green",
            "dominant_hex": "#1E4D3B",
            "thumbnail_url": "https://images.unsplash.com/photo-1589756823695-278bc923f962?w=700&auto=format&fit=crop&q=80",
            "images": json.dumps(["https://images.unsplash.com/photo-1589756823695-278bc923f962?w=700&auto=format&fit=crop&q=80"]),
            "rating": 4.9,
            "style_compatibility_base": 98,
            "is_featured": True,
            "skus": [
                {"sku_code": "MD-TIE-GRN-OS", "size": "One Size", "color": "Emerald Green", "color_hex": "#1E4D3B", "stock_level": 30}
            ]
        },
        {
            "brand_id": brand_md.id,
            "category_id": cat_accessories.id,
            "title": "100% Mulberry Silk Pocket Square",
            "title_ar": "منديل جيب حريري فاخر",
            "slug": "mulberry-silk-pocket-square-ivory",
            "description": "Hand-rolled edge Italian silk pocket square in delicate ivory with champagne contrast border.",
            "description_ar": "منديل جيب حريري بحواف ملفوفة يدوياً باللون العاجي ولمسات الشامبين.",
            "base_price": 45.0,
            "currency": "USD",
            "material": "100% Silk",
            "care_instructions": "Dry Clean Only",
            "style_tags": json.dumps(["formal", "wedding", "quiet_luxury"]),
            "occasion_tags": json.dumps(["wedding", "formal", "party"]),
            "color_family": "Ivory Cream",
            "dominant_hex": "#F5F2EB",
            "thumbnail_url": "https://images.unsplash.com/photo-1598532163257-ae3c6b2524b6?w=700&auto=format&fit=crop&q=80",
            "images": json.dumps(["https://images.unsplash.com/photo-1598532163257-ae3c6b2524b6?w=700&auto=format&fit=crop&q=80"]),
            "rating": 4.8,
            "style_compatibility_base": 95,
            "is_featured": False,
            "skus": [
                {"sku_code": "MD-PSQ-IVR-OS", "size": "One Size", "color": "Ivory Cream", "color_hex": "#F5F2EB", "stock_level": 25}
            ]
        },
        {
            "brand_id": brand_md.id,
            "category_id": cat_accessories.id,
            "title": "Italian Full-Grain Leather Dress Belt",
            "title_ar": "حزام جلد إيطالي فاخر للمناسبات والبدلات",
            "slug": "italian-full-grain-leather-dress-belt",
            "description": "Hand-buffed Italian bridle leather belt with understated brushed silver buckle.",
            "description_ar": "حزام جلد إيطالي ناعم بإبزيم فضي أنيق يناسب البناطيل الرسمية والتشينو.",
            "base_price": 85.0,
            "currency": "USD",
            "material": "100% Full-Grain Leather",
            "care_instructions": "Condition with Leather Cream",
            "style_tags": json.dumps(["formal", "smart_casual", "quiet_luxury"]),
            "occasion_tags": json.dumps(["wedding", "work", "business", "formal"]),
            "color_family": "Ebony Black",
            "dominant_hex": "#111111",
            "thumbnail_url": "https://images.unsplash.com/photo-1624222247344-550fb60583dc?w=700&auto=format&fit=crop&q=80",
            "images": json.dumps(["https://images.unsplash.com/photo-1624222247344-550fb60583dc?w=700&auto=format&fit=crop&q=80"]),
            "rating": 4.8,
            "style_compatibility_base": 96,
            "is_featured": False,
            "skus": [
                {"sku_code": "MD-BLT-BLK-90", "size": "90cm (32)", "color": "Ebony Black", "color_hex": "#111111", "stock_level": 20}
            ]
        },
        {
            "brand_id": brand_reiss.id,
            "category_id": cat_accessories.id,
            "title": "Structured Leather Evening Minaudiere Clutch",
            "title_ar": "حقيبة كلاتش سهرة جلدية بهيكل صلب وإطار ذهبي",
            "slug": "structured-leather-evening-minaudiere-clutch",
            "description": "Sculptural box clutch in black lizard-embossed leather with polished gold clasp and chain strap.",
            "description_ar": "حقيبة كلاتش مسائية فاخرة بلمسات ذهبية براقة وسلسلة كتف رفيعة.",
            "base_price": 180.0,
            "currency": "USD",
            "material": "100% Embossed Leather & Gold Plated Brass",
            "care_instructions": "Store in Dust Bag",
            "style_tags": json.dumps(["quiet_luxury", "evening", "formal"]),
            "occasion_tags": json.dumps(["wedding", "party", "gala", "dinner"]),
            "color_family": "Black & Gold",
            "dominant_hex": "#C5A059",
            "thumbnail_url": "https://images.unsplash.com/photo-1584917865442-de89df76afd3?w=700&auto=format&fit=crop&q=80",
            "images": json.dumps(["https://images.unsplash.com/photo-1584917865442-de89df76afd3?w=700&auto=format&fit=crop&q=80"]),
            "rating": 4.9,
            "style_compatibility_base": 97,
            "is_featured": False,
            "skus": [
                {"sku_code": "REISS-CLT-GLD-OS", "size": "One Size", "color": "Black & Gold", "color_hex": "#C5A059", "stock_level": 12}
            ]
        },
        {
            "brand_id": brand_arket.id,
            "category_id": cat_accessories.id,
            "title": "Classic Chronograph Leather Watch",
            "title_ar": "ساعة كرونوغراف كلاسيكية بسوار جلد طبيعي",
            "slug": "classic-chronograph-leather-watch",
            "description": "Timeless 38mm stainless steel chronograph with sapphire crystal and midnight blue dial.",
            "description_ar": "ساعة يد كلاسيكية بتصميم اسكندنافي أنيق وسوار جلدي فاخر.",
            "base_price": 290.0,
            "currency": "USD",
            "material": "Stainless Steel & Italian Leather",
            "care_instructions": "Water Resistant 5 ATM",
            "style_tags": json.dumps(["smart_casual", "quiet_luxury", "formal"]),
            "occasion_tags": json.dumps(["work", "business", "dinner", "wedding"]),
            "color_family": "Midnight Blue & Silver",
            "dominant_hex": "#1B1F3B",
            "thumbnail_url": "https://images.unsplash.com/photo-1522335789203-aabd1fc54bc9?w=700&auto=format&fit=crop&q=80",
            "images": json.dumps(["https://images.unsplash.com/photo-1522335789203-aabd1fc54bc9?w=700&auto=format&fit=crop&q=80"]),
            "rating": 4.9,
            "style_compatibility_base": 96,
            "is_featured": False,
            "skus": [
                {"sku_code": "ARK-WTC-SLV-OS", "size": "One Size", "color": "Midnight Blue", "color_hex": "#1B1F3B", "stock_level": 8}
            ]
        }
    ]

    product_objs = []
    sku_objs = []
    for p_data in products_seed:
        skus_data = p_data.pop("skus")
        prod = Product(**p_data)
        db.add(prod)
        db.flush()
        product_objs.append(prod)

        for s_data in skus_data:
            sku = ProductSKU(product_id=prod.id, **s_data)
            db.add(sku)
            sku_objs.append(sku)
    db.flush()

    # 6. Physical Stores (for BOPIS)
    stores_data = [
        {
            "brand_id": brand_objs[0].id,
            "name": "Massimo Dutti — The Dubai Mall",
            "name_ar": "ماسيمو دوتي — دبي مول",
            "address": "Fashion Avenue, Level 1, Financial Center Rd",
            "city": "Dubai",
            "country": "UAE",
            "latitude": 25.1972,
            "longitude": 55.2744,
            "phone": "+97143398700",
            "pickup_instructions": "Visit the Fashion Avenue VIP Concierge desk. Show digital pickup QR.",
            "is_bopis_enabled": True
        },
        {
            "brand_id": brand_objs[0].id,
            "name": "Massimo Dutti — Mall of the Emirates",
            "name_ar": "ماسيمو دوتي — مول الإمارات",
            "address": "Ground Floor, Central Galleria",
            "city": "Dubai",
            "country": "UAE",
            "latitude": 25.1181,
            "longitude": 55.2006,
            "phone": "+97143410123",
            "pickup_instructions": "Head to counter #2 near fitting rooms with confirmation code.",
            "is_bopis_enabled": True
        },
        {
            "brand_id": brand_objs[1].id,
            "name": "COS — Kingdom Centre",
            "name_ar": "كوس — مركز المملكة",
            "address": "King Fahd Rd, Al Olaya",
            "city": "Riyadh",
            "country": "Saudi Arabia",
            "latitude": 24.7115,
            "longitude": 46.6744,
            "phone": "+966112111000",
            "pickup_instructions": "BOPIS counter located at 1st floor entrance.",
            "is_bopis_enabled": True
        }
    ]

    store_objs = []
    for s in stores_data:
        store = StoreLocation(**s)
        db.add(store)
        store_objs.append(store)
    db.flush()

    # Add store inventory for each SKU
    for sku in sku_objs:
        for store in store_objs:
            inv = StoreInventory(
                store_id=store.id,
                sku_id=sku.id,
                quantity=6,
                reserved_quantity=0
            )
            db.add(inv)
    db.flush()

    # 7. Seed Consumer Wardrobe Items (G4)
    wardrobe_seed = [
        {
            "user_id": consumer_user.id,
            "title": "Structured Navy Travel Blazer",
            "category": "Outerwear",
            "subcategory": "Blazer",
            "color_name": "Navy Blue",
            "color_hex": "#1B1F3B",
            "pattern": "Solid",
            "brand_name": "Massimo Dutti",
            "image_url": "https://images.unsplash.com/photo-1594938298603-c8148c4dae35?w=500&auto=format&fit=crop&q=80",
            "ai_tags": json.dumps(["Tailored", "Wool Blend", "Wrinkle Resistant"]),
            "occasions": json.dumps(["work", "dinner"]),
            "wear_frequency": "favorite",
            "wear_count": 18,
            "purchase_price": 280.0,
            "is_favorite": True
        },
        {
            "user_id": consumer_user.id,
            "title": "Crisp White Linen Shirt",
            "category": "Tops",
            "subcategory": "Linen Shirt",
            "color_name": "Optic White",
            "color_hex": "#FAF9F6",
            "pattern": "Solid",
            "brand_name": "COS",
            "image_url": "https://images.unsplash.com/photo-1602810318383-e386cc2a3ccf?w=500&auto=format&fit=crop&q=80",
            "ai_tags": json.dumps(["Breathable", "Pure Linen", "Summer Essential"]),
            "occasions": json.dumps(["casual", "weekend", "work"]),
            "wear_frequency": "regular",
            "wear_count": 12,
            "purchase_price": 95.0,
            "is_favorite": True
        }
    ]
    for w in wardrobe_seed:
        db.add(WardrobeItem(**w))
    db.flush()

    # 8. Seed Saved Outfits (G2.3)
    outfit1 = Outfit(
        user_id=consumer_user.id,
        title="Elevated Metropolitan Boardroom",
        description="A pristine combination of Italian wool tailoring and crisp poplin.",
        occasion="Work & Business",
        total_price=384.0,
        compatibility_score=97,
        color_palette=json.dumps(["#1B1F3B", "#FAF9F6", "#D8C7B5"]),
        style_tags=json.dumps(["Smart Casual", "Quiet Luxury"]),
        is_saved=True,
        is_system_curated=False
    )
    db.add(outfit1)
    db.flush()

    db.add(OutfitItem(outfit_id=outfit1.id, product_id=product_objs[0].id, product_sku_id=sku_objs[1].id, position="outerwear", sort_order=0))
    db.add(OutfitItem(outfit_id=outfit1.id, product_id=product_objs[4].id, product_sku_id=sku_objs[11].id, position="top", sort_order=1))

    # 9. Seed Sponsored Placement (G6)
    placement1 = SponsoredPlacement(
        brand_id=brand_objs[0].id,
        product_id=product_objs[0].id,
        placement_type="stylist_featured",
        bid_amount_per_click=0.75,
        daily_budget=100.0,
        spent_today=32.5,
        status="active",
        impressions=3820,
        clicks=428,
        conversions=54,
        revenue_generated=15606.0
    )
    db.add(placement1)

    # 10. Seed Platform Order for tracking demo (G5.3)
    sample_order = Order(
        order_number="CONF-8821094A",
        user_id=consumer_user.id,
        total_amount=384.0,
        subtotal_amount=384.0,
        discount_amount=0.0,
        tax_amount=19.2,
        shipping_amount=0.0,
        currency="USD",
        payment_method="bnpl_tabby",
        payment_status="paid",
        payment_installments=4,
        fulfillment_type="bopis",
        bopis_store_id=store_objs[0].id,
        bopis_pickup_code="PICKUP-8821",
        shipping_recipient_name="Layla Al-Mansoor",
        shipping_address_line="Fashion Avenue, The Dubai Mall",
        shipping_city="Dubai",
        shipping_country="UAE",
        shipping_phone="+971501234567",
        tracking_number="TRK-CONF-8821094",
        status="processing",
        try_on_assisted=True,
        stylist_assisted=True,
        idempotency_key="idemp_seed_order_001"
    )
    db.add(sample_order)
    db.flush()

    db.add(OrderItem(
        order_id=sample_order.id,
        product_sku_id=sku_objs[1].id,
        product_id=product_objs[0].id,
        brand_id=brand_objs[0].id,
        product_title="Tailored Italian Wool Double-Breasted Blazer",
        brand_name="Massimo Dutti",
        size="M",
        color="Navy Blue",
        unit_price=289.0,
        quantity=1,
        subtotal=289.0,
        is_returned=False
    ))
    db.add(OrderItem(
        order_id=sample_order.id,
        product_sku_id=sku_objs[11].id,
        product_id=product_objs[4].id,
        brand_id=brand_objs[1].id,
        product_title="Relaxed Organic Poplin Oxford Shirt",
        brand_name="COS",
        size="M",
        color="Optic White",
        unit_price=95.0,
        quantity=1,
        subtotal=95.0,
        is_returned=False
    ))

    db.commit()
    db.close()
    print("✅ CONFIT Database Seeded Successfully with 24+ items across all slots and categories!")


if __name__ == "__main__":
    seed_database()
