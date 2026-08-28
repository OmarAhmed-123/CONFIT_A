from typing import Dict
from backend.app.providers.payment.schemas import PaymentMethodOption, MarketPaymentCapabilitiesResponse


class MarketPaymentCapabilityRegistry:
    """Registry defining live, active, and compliant payment rails per country code."""

    MARKET_CURRENCIES = {
        "EG": "EGP",
        "AE": "AED",
        "SA": "SAR",
        "QA": "QAR",
        "KW": "KWD",
        "BH": "BHD",
        "OM": "OMR",
        "US": "USD",
        "GLOBAL": "USD"
    }

    PAYMENT_CATALOG: Dict[str, PaymentMethodOption] = {
        "card": PaymentMethodOption(
            id="card",
            title_en="Credit / Debit Card",
            title_ar="بطاقة ائتمانية / بنكية",
            description_en="Visa, Mastercard, American Express with 3D Secure",
            description_ar="فيزا، ماستركارد، أمريكان إكسبريس مع حماية ثلاثية الأبعاد",
            icon_name="card",
            provider_name="stripe_or_paymob",
            is_live=True,
            supported_countries=["EG", "AE", "SA", "QA", "KW", "BH", "OM", "US", "GLOBAL"]
        ),
        "bnpl_tabby": PaymentMethodOption(
            id="bnpl_tabby",
            title_en="Tabby — Split in 4",
            title_ar="تابي — قسّم على 4 دفعات",
            description_en="Split in 4 interest-free monthly payments. Sharia compliant.",
            description_ar="قسّم على 4 دفعات شهرية بدون فوائد أو رسوم تأخير. متوافق مع الشريعة.",
            icon_name="tabby",
            provider_name="tabby",
            is_live=True,
            supported_countries=["AE", "SA", "KW", "BH", "QA", "EG"],
            installment_available=True,
            installments_count=4
        ),
        "bnpl_tamara": PaymentMethodOption(
            id="bnpl_tamara",
            title_en="Tamara — Split in 4",
            title_ar="تمارا — قسّم على 4 دفعات",
            description_en="Split in 4 payments with 0% interest and no hidden fees.",
            description_ar="قسّم على 4 دفعات شهرية بدون فوائد وبدون رسوم خفية.",
            icon_name="tamara",
            provider_name="tamara",
            is_live=True,
            supported_countries=["SA", "AE", "KW"],
            installment_available=True,
            installments_count=4
        ),
        "apple_pay": PaymentMethodOption(
            id="apple_pay",
            title_en="Apple Pay",
            title_ar="أبل باي",
            description_en="Instant 1-tap biometric checkout via Touch ID / Face ID",
            description_ar="دفع فوري ببصمة الإصبع أو الوجه مع أبل باي",
            icon_name="apple_pay",
            provider_name="apple_pay_psp",
            is_live=True,
            supported_countries=["AE", "SA", "QA", "KW", "BH", "OM", "US"]
        ),
        "vodafone_cash": PaymentMethodOption(
            id="vodafone_cash",
            title_en="Smart Mobile Wallets (Vodafone / Orange / Etisalat Cash)",
            title_ar="المحافظ الإلكترونية (فودافون كاش / أورنج / اتصالات / وي)",
            description_en="Pay directly with your local Egyptian mobile wallet via Paymob PSP",
            description_ar="ادفع مباشرة من محفظتك الإلكترونية المصرية عبر بوابة باي موب",
            icon_name="wallet",
            provider_name="paymob_wallets",
            is_live=True,
            supported_countries=["EG"]
        ),
        "instapay_bridge": PaymentMethodOption(
            id="instapay_bridge",
            title_en="InstaPay Instant Bank Transfer (PSP Bridge)",
            title_ar="التحويل البنكي الفوري عبر إنستاباي (بوابة الدفع)",
            description_en="Instant Egyptian IPN transfer via authorized PSP banking bridge with automated reconciliation",
            description_ar="تحويل بنكي فوري عبر شبكة المدفوعات اللحظية IPN المعتمدة مع مطابقة آلية",
            icon_name="instapay",
            provider_name="paymob_fawry_bridge",
            is_live=True,
            supported_countries=["EG"],
            requires_redirect=True
        ),
        "cod": PaymentMethodOption(
            id="cod",
            title_en="Cash on Delivery (COD)",
            title_ar="الدفع نقدًا عند الاستلام",
            description_en="Pay in cash at your doorstep upon receiving your luxury package",
            description_ar="ادفع نقدًا عند استلام شحنتك الفاخرة على باب منزلك",
            icon_name="cod",
            provider_name="confit_logistics",
            is_live=True,
            supported_countries=["EG", "AE", "SA", "KW", "BH", "OM"]
        )
    }

    @classmethod
    def get_capabilities_for_market(cls, country_code: str = "EG") -> MarketPaymentCapabilitiesResponse:
        code = country_code.upper() if country_code else "EG"
        currency = cls.MARKET_CURRENCIES.get(code, "USD")

        # Filter methods supported by this country
        methods = [
            m for m in cls.PAYMENT_CATALOG.values()
            if code in m.supported_countries or "GLOBAL" in m.supported_countries
        ]

        disclaimer_en = (
            f"All transactions in {code} are processed in compliance with local central bank regulations "
            "and PCI-DSS tokenization standards."
        )
        disclaimer_ar = (
            f"تتم جميع المعاملات في {code} بما يتوافق مع تعليمات البنوك المركزية ومعايير التشفير الآمن PCI-DSS."
        )

        return MarketPaymentCapabilitiesResponse(
            market_code=code,
            currency_code=currency,
            available_methods=methods,
            cod_eligible=code in ["EG", "AE", "SA"],
            bopis_eligible=code in ["EG", "AE", "SA"],
            disclaimer_en=disclaimer_en,
            disclaimer_ar=disclaimer_ar
        )
