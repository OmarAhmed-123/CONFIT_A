from typing import Dict

from backend.app.providers.payment.schemas import PaymentMethodOption, MarketPaymentCapabilitiesResponse

import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Dict, Optional

from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.core.money import money_mul, quantize_money

DEFAULT_PRICING_CURRENCY = "USD"


@dataclass(frozen=True)
class SettlementResolution:
    """The one answer checkout needs about money in a market.

    ``currency`` is what gets stamped on the order / payment / payment
    transaction; ``rate`` converts an amount denominated in the catalog price
    book into that currency (Decimal("1") when they are the same currency).
    ``converted`` distinguishes "settling in the market's own currency" from
    "settling in the pricing currency", and ``reason`` records why, so a
    market that should have converted but did not is diagnosable from the
    resolution alone instead of from a wrong-looking total.
    """

    market_code: str
    market_currency: str
    pricing_currency: str
    currency: str
    rate: Decimal
    converted: bool
    reason: str

    def convert(self, amount: Decimal) -> Decimal:
        """Exact Decimal conversion, quantized to the money scale.

        A no-op when the settlement currency IS the pricing currency, so the
        default configuration cannot perturb an existing Decimal result by so
        much as a rounding step.
        """
        if not self.converted:
            return quantize_money(amount)
        return quantize_money(money_mul(amount, self.rate))


class MarketSettlement:
    """Currency resolution for settlement. Mixed into the capability registry
    below so there is exactly one market authority in the codebase."""

    # CheckoutRequest.country still defaults to the NAME "UAE" rather than the
    # ISO-3166 code "AE", and shipping addresses are free text. A market
    # authority that only understood exact ISO codes would silently resolve
    # those callers to the fallback currency, so the common spellings are
    # normalised here - once, in one place.
    COUNTRY_ALIASES = {
        "UAE": "AE", "UNITED ARAB EMIRATES": "AE", "EMIRATES": "AE",
        "USA": "US", "US": "US", "UNITED STATES": "US", "UNITED STATES OF AMERICA": "US",
        "EGYPT": "EG", "MISR": "EG",
        "SAUDI ARABIA": "SA", "KSA": "SA",
        "KUWAIT": "KW", "QATAR": "QA", "BAHRAIN": "BH", "OMAN": "OM",
    }

    @classmethod
    def market_code(cls, country_code: Optional[str]) -> str:
        """Normalise a country input to the registry's market code."""
        code = (country_code or "").strip().upper() or "EG"
        return cls.COUNTRY_ALIASES.get(code, code)

    @classmethod
    def pricing_currency(cls) -> str:
        """Currency the catalog price book is denominated in.

        Every seeded/migrated product carries ``currency='USD'`` today, so the
        default is USD - but it is configuration, not a literal scattered
        through the money path.
        """
        raw = (getattr(settings, "PRICING_CURRENCY", "") or "").strip().upper()
        return raw or DEFAULT_PRICING_CURRENCY

    @classmethod
    def currency_for_market(cls, country_code: Optional[str]) -> str:
        """The currency a market transacts in, per the capability registry."""
        code = cls.market_code(country_code)
        currencies = getattr(cls, "MARKET_CURRENCIES", {})
        return currencies.get(code, cls.pricing_currency())

    @classmethod
    def fx_rates(cls) -> Dict[str, Decimal]:
        """Configured rates FROM the pricing currency, e.g. {"EGP": "48.5"}.

        Parsed defensively: a malformed table must never take checkout down,
        and a malformed *entry* must never be silently treated as 1.0 (that
        would mislabel money). Bad entries are dropped and logged.
        """
        raw = getattr(settings, "MARKET_FX_RATES", "") or ""
        if isinstance(raw, dict):
            parsed: Dict[str, object] = raw
        else:
            text = str(raw).strip()
            if not text:
                return {}
            try:
                parsed = json.loads(text)
            except (TypeError, ValueError) as exc:
                logger.error(
                    "market_fx_rates_unparseable",
                    error=f"{type(exc).__name__}: {exc}"[:200],
                    action_required="MARKET_FX_RATES must be a JSON object of CURRENCY->rate",
                )
                return {}
        if not isinstance(parsed, dict):
            logger.error("market_fx_rates_wrong_shape", got=type(parsed).__name__)
            return {}

        rates: Dict[str, Decimal] = {}
        for key, value in parsed.items():
            code = str(key).strip().upper()
            try:
                rate = Decimal(str(value).strip())
            except (InvalidOperation, AttributeError, TypeError, ValueError):
                logger.error("market_fx_rate_invalid", currency=code, value=str(value)[:40])
                continue
            if not rate.is_finite() or rate <= 0:
                logger.error("market_fx_rate_non_positive", currency=code, value=str(rate))
                continue
            rates[code] = rate
        return rates

    @classmethod
    def resolve_settlement(cls, country_code: Optional[str]) -> SettlementResolution:
        """Resolve the settlement currency + rate for a market. Never raises."""
        pricing = cls.pricing_currency()
        code = cls.market_code(country_code)
        market_currency = cls.currency_for_market(code)

        if market_currency == pricing:
            return SettlementResolution(
                market_code=code, market_currency=market_currency, pricing_currency=pricing,
                currency=pricing, rate=Decimal("1"), converted=False,
                reason="market_currency_is_pricing_currency",
            )

        rate = cls.fx_rates().get(market_currency)
        if rate is None:
            # Fail SAFE, not silent: settle in the pricing currency (today's
            # behaviour, amounts and label stay consistent) and log loudly so
            # the missing treasury input is visible instead of shipping an
            # order stamped with a currency its amounts were never priced in.
            logger.warn(
                "market_fx_rate_not_configured",
                market=code,
                market_currency=market_currency,
                pricing_currency=pricing,
                action_required=(
                    f"set MARKET_FX_RATES with a {market_currency} rate to settle "
                    f"{code} in its own currency"
                ),
            )
            return SettlementResolution(
                market_code=code, market_currency=market_currency, pricing_currency=pricing,
                currency=pricing, rate=Decimal("1"), converted=False,
                reason="fx_rate_not_configured",
            )

        return SettlementResolution(
            market_code=code, market_currency=market_currency, pricing_currency=pricing,
            currency=market_currency, rate=rate, converted=True,
            reason="fx_rate_configured",
        )


class MarketPaymentCapabilityRegistry(MarketSettlement):
    """Registry defining live, active, and compliant payment rails per country code.

    Also the single authority for *which currency a market settles in* - see
    :class:`MarketSettlement`. Money and payment capability for a market are
    one decision, so they live in one registry.
    """

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
        code = cls.market_code(country_code)
        currency = cls.currency_for_market(code)

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
