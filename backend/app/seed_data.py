import json
from datetime import datetime, timezone
from sqlalchemy.orm import Session, sessionmaker
from backend.app.core.database import SessionLocal, Base, engine
from backend.app.core.security import get_password_hash, encrypt_sensitive_data
from backend.app.models.user import User, UserRole, BrandProfile, AuditLog
from backend.app.models.profile import UserStyleProfile
from backend.app.models.catalog import Category, Product, ProductSKU, StoreLocation, StoreInventory
from backend.app.models.stylist import StylistSession, StylistMessage, Outfit, OutfitItem
from backend.app.models.wardrobe import WardrobeItem, WardrobeGapAnalysis
from backend.app.models.commerce import Cart, CartItem, Order, OrderItem
from backend.app.models.brand_analytics import SponsoredPlacement, StyleHeatmapAggregate


def seed_database(target_engine=None):
    active_engine = target_engine or engine
    Base.metadata.drop_all(bind=active_engine)
    Base.metadata.create_all(bind=active_engine)
    
    SessionMaker = sessionmaker(autocommit=False, autoflush=False, bind=active_engine)
    db: Session = SessionMaker()

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

    # 5. Products & SKUs
    products_seed = [
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
                "https://images.unsplash.com/photo-1594938298603-c8148c4dae35?w=700&auto=format&fit=crop&q=80"
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
            "description_ar": "سترة سهرة فاخرة بياقة ساتان مدببة وتصميم أنيق للمناسبات الرسمية.",
            "base_price": 395.0,
            "currency": "USD",
            "material": "Wool Silk Blend",
            "care_instructions": "Dry Clean Only",
            "style_tags": json.dumps(["formal", "evening", "quiet_luxury"]),
            "occasion_tags": json.dumps(["wedding", "gala", "black_tie", "party"]),
            "color_family": "Midnight Black",
            "dominant_hex": "#111111",
            "thumbnail_url": "https://images.unsplash.com/photo-1507679799987-c73779587ccf?w=700&auto=format&fit=crop&q=80",
            "images": json.dumps(["https://images.unsplash.com/photo-1507679799987-c73779587ccf?w=700&auto=format&fit=crop&q=80"]),
            "rating": 4.9,
            "style_compatibility_base": 98,
            "is_featured": True,
            "skus": [
                {"sku_code": "REISS-TUX-BLK-38", "size": "38", "color": "Midnight Black", "color_hex": "#111111", "stock_level": 8},
                {"sku_code": "REISS-TUX-BLK-40", "size": "40", "color": "Midnight Black", "color_hex": "#111111", "stock_level": 14}
            ]
        },
        {
            "brand_id": brand_cos.id,
            "category_id": cat_tops.id,
            "title": "Relaxed Organic Poplin Oxford Shirt",
            "title_ar": "قميص أكسفورد بوبلين عضوي بقصة مريحة",
            "slug": "relaxed-organic-poplin-oxford-shirt",
            "description": "Crisp organic cotton poplin tailored with clean French seams and pointed collar.",
            "description_ar": "قميص قطني ناعم وعضوي بقصة عصرية مريحة.",
            "base_price": 95.0,
            "currency": "USD",
            "material": "100% Organic Cotton",
            "care_instructions": "Machine Wash 30C",
            "style_tags": json.dumps(["smart_casual", "minimalist", "essential"]),
            "occasion_tags": json.dumps(["work", "casual", "dinner", "wedding"]),
            "color_family": "Optic White",
            "dominant_hex": "#FAF9F6",
            "thumbnail_url": "https://images.unsplash.com/photo-1602810318383-e386cc2a3ccf?w=700&auto=format&fit=crop&q=80",
            "images": json.dumps(["https://images.unsplash.com/photo-1602810318383-e386cc2a3ccf?w=700&auto=format&fit=crop&q=80"]),
            "rating": 4.8,
            "style_compatibility_base": 95,
            "is_featured": False,
            "skus": [
                {"sku_code": "COS-SHR-WHT-S", "size": "S", "color": "Optic White", "color_hex": "#FAF9F6", "stock_level": 15},
                {"sku_code": "COS-SHR-WHT-M", "size": "M", "color": "Optic White", "color_hex": "#FAF9F6", "stock_level": 20},
                {"sku_code": "COS-SHR-WHT-L", "size": "L", "color": "Optic White", "color_hex": "#FAF9F6", "stock_level": 12}
            ]
        },
        {
            "brand_id": brand_md.id,
            "category_id": cat_bottoms.id,
            "title": "Pleated Tapered Virgin Wool Trousers",
            "title_ar": "بنطال صوف فيرجن بقصة مريحة وكسرات",
            "slug": "pleated-tapered-virgin-wool-trousers",
            "description": "Double-pleated formal trousers featuring adjustable side tabs and a subtle tapered hem.",
            "description_ar": "بنطال صوف أنيق بكسرات متقنة وتفصيل راقٍ يناسب الإطلالات الرسمية والعملية.",
            "base_price": 165.0,
            "currency": "USD",
            "material": "100% Virgin Wool",
            "care_instructions": "Dry Clean",
            "style_tags": json.dumps(["formal", "tailored", "smart_casual"]),
            "occasion_tags": json.dumps(["wedding", "work", "business", "dinner"]),
            "color_family": "Navy Blue",
            "dominant_hex": "#1B1F3B",
            "thumbnail_url": "https://images.unsplash.com/photo-1624378439575-d8705ad7ae80?w=700&auto=format&fit=crop&q=80",
            "images": json.dumps(["https://images.unsplash.com/photo-1624378439575-d8705ad7ae80?w=700&auto=format&fit=crop&q=80"]),
            "rating": 4.8,
            "style_compatibility_base": 94,
            "is_featured": False,
            "skus": [
                {"sku_code": "MD-TRS-NVY-30", "size": "30", "color": "Navy Blue", "color_hex": "#1B1F3B", "stock_level": 10},
                {"sku_code": "MD-TRS-NVY-32", "size": "32", "color": "Navy Blue", "color_hex": "#1B1F3B", "stock_level": 15},
                {"sku_code": "MD-TRS-NVY-34", "size": "34", "color": "Navy Blue", "color_hex": "#1B1F3B", "stock_level": 8}
            ]
        },
        {
            "brand_id": brand_reiss.id,
            "category_id": cat_dresses.id,
            "title": "Silk Slip Column Maxi Dress with Drape Neckline",
            "title_ar": "فستان ماكسي حرير بتصميم عمودي وياقة منسدلة",
            "slug": "silk-slip-column-maxi-dress",
            "description": "Floor-sweeping column gown rendered in pure mulberry silk satin with a fluid cowl neckline.",
            "description_ar": "فستان سهرة ماكسي فاخر من الحرير الطبيعي بياقة منسدلة ناعمة.",
            "base_price": 340.0,
            "currency": "USD",
            "material": "100% Mulberry Silk",
            "care_instructions": "Specialist Dry Clean",
            "style_tags": json.dumps(["formal", "evening", "glamour", "quiet_luxury"]),
            "occasion_tags": json.dumps(["wedding", "party", "gala", "dinner"]),
            "color_family": "Champagne Gold",
            "dominant_hex": "#D4AF37",
            "thumbnail_url": "https://images.unsplash.com/photo-1595777457583-95e059d581b8?w=700&auto=format&fit=crop&q=80",
            "images": json.dumps(["https://images.unsplash.com/photo-1595777457583-95e059d581b8?w=700&auto=format&fit=crop&q=80"]),
            "rating": 4.9,
            "style_compatibility_base": 98,
            "is_featured": True,
            "skus": [
                {"sku_code": "REISS-DRS-GLD-6", "size": "6", "color": "Champagne Gold", "color_hex": "#D4AF37", "stock_level": 9},
                {"sku_code": "REISS-DRS-GLD-8", "size": "8", "color": "Champagne Gold", "color_hex": "#D4AF37", "stock_level": 14}
            ]
        },
        {
            "brand_id": brand_md.id,
            "category_id": cat_footwear.id,
            "title": "Goodyear Welted Leather Oxford Shoes",
            "title_ar": "حذاء أكسفورد جلد بحياكة جوديير كلاسيكية",
            "slug": "goodyear-welted-leather-oxford-shoes",
            "description": "Full-grain calfskin oxford shoes with closed lacing and durable Goodyear welted leather sole.",
            "description_ar": "حذاء كلاسيكي من الجلد الطبيعي الفاخر بنعل متين وحياكة راقية.",
            "base_price": 245.0,
            "currency": "USD",
            "material": "100% Full-Grain Calfskin",
            "care_instructions": "Polish with Natural Wax",
            "style_tags": json.dumps(["formal", "tailored", "smart_casual"]),
            "occasion_tags": json.dumps(["wedding", "work", "business", "dinner"]),
            "color_family": "Obsidian Black",
            "dominant_hex": "#111111",
            "thumbnail_url": "https://images.unsplash.com/photo-1614252235316-8c857d38b5f4?w=700&auto=format&fit=crop&q=80",
            "images": json.dumps(["https://images.unsplash.com/photo-1614252235316-8c857d38b5f4?w=700&auto=format&fit=crop&q=80"]),
            "rating": 4.9,
            "style_compatibility_base": 97,
            "is_featured": False,
            "skus": [
                {"sku_code": "MD-OXF-BLK-41", "size": "41", "color": "Obsidian Black", "color_hex": "#111111", "stock_level": 8},
                {"sku_code": "MD-OXF-BLK-42", "size": "42", "color": "Obsidian Black", "color_hex": "#111111", "stock_level": 12},
                {"sku_code": "MD-OXF-BLK-43", "size": "43", "color": "Obsidian Black", "color_hex": "#111111", "stock_level": 6}
            ]
        },
        {
            "brand_id": brand_reiss.id,
            "category_id": cat_footwear.id,
            "title": "Strappy Metallic Leather Heeled Sandals",
            "title_ar": "صندل بكعب وسيور جلدية ميتاليك",
            "slug": "strappy-metallic-leather-heeled-sandals",
            "description": "Minimalist stiletto sandals with delicate ankle wrap straps and metallic gold finish.",
            "description_ar": "صندل مسائي فاخر بسيور رفيعة وكعب عالٍ أنيق.",
            "base_price": 250.0,
            "currency": "USD",
            "material": "100% Metallic Leather",
            "care_instructions": "Store in Dust Bag",
            "style_tags": json.dumps(["evening", "formal", "glamour"]),
            "occasion_tags": json.dumps(["wedding", "party", "gala", "dinner"]),
            "color_family": "Metallic Gold",
            "dominant_hex": "#C5A059",
            "thumbnail_url": "https://images.unsplash.com/photo-1543163521-1bf539c55dd2?w=700&auto=format&fit=crop&q=80",
            "images": json.dumps(["https://images.unsplash.com/photo-1543163521-1bf539c55dd2?w=700&auto=format&fit=crop&q=80"]),
            "rating": 4.8,
            "style_compatibility_base": 96,
            "is_featured": False,
            "skus": [
                {"sku_code": "REISS-SND-GLD-38", "size": "38", "color": "Metallic Gold", "color_hex": "#C5A059", "stock_level": 7},
                {"sku_code": "REISS-SND-GLD-39", "size": "39", "color": "Metallic Gold", "color_hex": "#C5A059", "stock_level": 11}
            ]
        },
        {
            "brand_id": brand_reiss.id,
            "category_id": cat_accessories.id,
            "title": "Silk Jacquard Evening Necktie",
            "title_ar": "ربطة عنق حريرية جاكار للمناسبات",
            "slug": "silk-jacquard-evening-necktie",
            "description": "Pure emerald silk necktie featuring subtle geometric jacquard weave.",
            "description_ar": "ربطة عنق فاخرة من الحرير الطبيعي الأخضر الزمردي.",
            "base_price": 75.0,
            "currency": "USD",
            "material": "100% Mulberry Silk",
            "care_instructions": "Dry Clean Only",
            "style_tags": json.dumps(["formal", "tailored", "smart_casual"]),
            "occasion_tags": json.dumps(["wedding", "work", "business", "dinner"]),
            "color_family": "Emerald Green",
            "dominant_hex": "#2D4A3E",
            "thumbnail_url": "https://images.unsplash.com/photo-1589756823695-278bc923f962?w=700&auto=format&fit=crop&q=80",
            "images": json.dumps(["https://images.unsplash.com/photo-1589756823695-278bc923f962?w=700&auto=format&fit=crop&q=80"]),
            "rating": 4.9,
            "style_compatibility_base": 97,
            "is_featured": False,
            "skus": [
                {"sku_code": "REISS-TIE-EMR-OS", "size": "One Size", "color": "Emerald Green", "color_hex": "#2D4A3E", "stock_level": 25}
            ]
        },
        {
            "brand_id": brand_reiss.id,
            "category_id": cat_accessories.id,
            "title": "Structured Metallic Evening Box Clutch",
            "title_ar": "حقيبة يد كلاتش مسائية ميتاليك",
            "slug": "structured-metallic-evening-box-clutch",
            "description": "Structured evening minaudière clutch in gold embossed leather with polished clasp.",
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
            "pickup_instructions": "Visit Fashion Avenue VIP Concierge desk.",
            "is_bopis_enabled": True
        }
    ]

    store_objs = []
    for s in stores_data:
        store = StoreLocation(**s)
        db.add(store)
        store_objs.append(store)
    db.flush()

    for sku in sku_objs:
        for store in store_objs:
            inv = StoreInventory(store_id=store.id, sku_id=sku.id, quantity=6, reserved_quantity=0)
            db.add(inv)
    db.flush()

    # 7. Wardrobe Item
    db.add(WardrobeItem(
        user_id=consumer_user.id,
        title="Structured Navy Travel Blazer",
        category="Outerwear",
        color_name="Navy Blue",
        color_hex="#1B1F3B",
        brand_name="Massimo Dutti",
        image_url="https://images.unsplash.com/photo-1594938298603-c8148c4dae35?w=500",
        purchase_price=280.0
    ))
    db.flush()

    # 8. Saved Outfit
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
    db.add(OutfitItem(outfit_id=outfit1.id, product_id=product_objs[2].id, product_sku_id=sku_objs[4].id, position="top", sort_order=1))

    # 9. Sponsored Placement
    db.add(SponsoredPlacement(
        brand_id=brand_objs[0].id,
        product_id=product_objs[0].id,
        placement_type="stylist_featured",
        bid_amount_per_click=0.75,
        daily_budget=100.0,
        spent_today=32.5,
        status="active"
    ))

    # 10. Sample Order
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
        fulfillment_type="bopis",
        bopis_store_id=store_objs[0].id,
        bopis_pickup_code="PICKUP-8821",
        shipping_recipient_name="Layla Al-Mansoor",
        shipping_address_line="Fashion Avenue, The Dubai Mall",
        shipping_city="Dubai",
        shipping_country="UAE",
        shipping_phone="+971501234567",
        tracking_number="TRK-CONF-8821094",
        status="processing"
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

    db.commit()
    db.close()
    print("✅ CONFIT Database Seeded Successfully!")


if __name__ == "__main__":
    seed_database()
