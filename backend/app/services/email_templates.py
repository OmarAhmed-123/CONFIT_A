"""Transactional email templates (task §16).

Rules encoded here:
  * every template returns ``(subject, html, text)`` — a plain-text alternative
    always exists (deliverability + accessibility);
  * all interpolated values are HTML-escaped, and subjects have CR/LF stripped
    (header-injection defence, task §20);
  * no secret other than the single-use action token appears — and the token
    only inside its one-time URL. Internal ids, roles and provider details are
    never exposed;
  * bilingual EN + AR blocks (the product ships RTL Arabic) and a responsive,
    table-free layout that renders in conservative mail clients;
  * links are built from settings.FRONTEND_BASE_URL by the CALLER and passed in
    already absolute, so no template can hardcode a development or staging
    host (see backend/tests/test_production_parity.py for the guard).
"""
from __future__ import annotations

import html as _html
from typing import Optional

BRAND_NAVY = "#0C0E1E"
BRAND_GOLD = "#C5A059"
BRAND_BG = "#F7F6F3"


def _e(value: Optional[str]) -> str:
    """HTML-escape any interpolated value (task §20 — template injection)."""
    return _html.escape(str(value if value is not None else ""), quote=True)


def _subject(value: str) -> str:
    """Strip CR/LF from a subject line (header injection)."""
    return " ".join(str(value).split("\r\n")).replace("\n", " ").strip()


def _layout(title_en: str, title_ar: str, body_en: str, body_ar: str) -> str:
    """Shared branded shell. EN block first, AR block second (dir=rtl)."""
    return f"""<!doctype html>
<html lang="en">
<body style="margin:0;padding:24px;background:{BRAND_BG};font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Tahoma,Arial,sans-serif;color:#1B1F3B;">
  <div style="max-width:560px;margin:0 auto;background:#ffffff;border-radius:18px;overflow:hidden;border:1px solid #E7E3DA;">
    <div style="background:{BRAND_NAVY};padding:22px 26px;">
      <div style="font-size:20px;letter-spacing:6px;color:{BRAND_GOLD};font-weight:700;">CONFIT</div>
      <div style="font-size:11px;color:#9AA1B4;margin-top:4px;">Where Style Meets Your Character</div>
    </div>
    <div style="padding:26px;">
      <h1 style="margin:0 0 14px;font-size:20px;color:{BRAND_NAVY};">{_e(title_en)}</h1>
      {body_en}
      <hr style="border:none;border-top:1px solid #EFEBE3;margin:24px 0;" />
      <div dir="rtl" style="text-align:right;">
        <h2 style="margin:0 0 12px;font-size:17px;color:{BRAND_NAVY};">{_e(title_ar)}</h2>
        {body_ar}
      </div>
    </div>
    <div style="background:#FBFAF7;padding:16px 26px;font-size:11px;color:#7A8095;border-top:1px solid #EFEBE3;">
      CONFIT · This is a transactional message about your account. Replies are not monitored.
      <br />كونفيت · رسالة معاملات تخص حسابك، ولا تتم متابعة الردود عليها.
    </div>
  </div>
</body>
</html>"""


def _button(url: str, label: str) -> str:
    return (
        f'<p style="margin:18px 0;"><a href="{_e(url)}" '
        f'style="display:inline-block;background:{BRAND_GOLD};color:{BRAND_NAVY};'
        f'font-weight:700;padding:12px 22px;border-radius:10px;text-decoration:none;'
        f'font-size:13px;">{_e(label)}</a></p>'
        f'<p style="margin:8px 0;font-size:12px;color:#7A8095;word-break:break-all;">{_e(url)}</p>'
    )


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

def render_verification_email(full_name: str, verify_url: str) -> tuple[str, str, str]:
    subject = _subject("Verify your CONFIT email / تأكيد بريدك الإلكتروني")
    text = (
        f"Welcome to CONFIT, {full_name}!\n\n"
        f"Confirm your email address to secure your account:\n{verify_url}\n\n"
        f"This link is valid for 24 hours and can be used once.\n\n— CONFIT"
    )
    html = _layout(
        "Confirm your email address",
        "أكّد بريدك الإلكتروني",
        f"<p style='font-size:14px;line-height:1.7;'>Hello {_e(full_name or 'there')},</p>"
        f"<p style='font-size:14px;line-height:1.7;'>Confirm your email address to secure your account. "
        f"The link is valid for 24 hours and can be used once.</p>"
        f"{_button(verify_url, 'Verify my email')}",
        f"<p style='font-size:14px;line-height:1.7;'>مرحبًا {_e(full_name or '')}،</p>"
        f"<p style='font-size:14px;line-height:1.7;'>أكّد بريدك الإلكتروني لتأمين حسابك. الرابط صالح 24 ساعة وللاستخدام مرة واحدة.</p>",
    )
    return subject, html, text


def render_verification_reminder_email(full_name: str, verify_url: str) -> tuple[str, str, str]:
    """Resend — same action, different framing so it never looks like a dupe bug."""
    subject = _subject("Reminder: verify your CONFIT email / تذكير: أكّد بريدك")
    text = (
        f"Hello {full_name},\n\n"
        f"You requested a new confirmation link for CONFIT.\n{verify_url}\n\n"
        f"Valid for 24 hours, single use. Earlier links have been invalidated.\n\n— CONFIT"
    )
    html = _layout(
        "Your new confirmation link",
        "رابط التأكيد الجديد",
        f"<p style='font-size:14px;line-height:1.7;'>Hello {_e(full_name or 'there')},</p>"
        f"<p style='font-size:14px;line-height:1.7;'>Here is the confirmation link you requested. "
        f"Any earlier link has been invalidated.</p>{_button(verify_url, 'Verify my email')}",
        f"<p style='font-size:14px;line-height:1.7;'>هذا هو رابط التأكيد الذي طلبته. تم إلغاء أي رابط سابق.</p>",
    )
    return subject, html, text


# ---------------------------------------------------------------------------
# Password lifecycle
# ---------------------------------------------------------------------------

def render_password_reset_email(full_name: str, reset_url: str, ttl_minutes: int = 30) -> tuple[str, str, str]:
    subject = _subject("Reset your CONFIT password / إعادة تعيين كلمة المرور")
    text = (
        f"Hello {full_name},\n\n"
        f"We received a request to reset your CONFIT password.\n"
        f"This link is valid for {ttl_minutes} minutes and can be used once:\n{reset_url}\n\n"
        f"If you did not request this, ignore this email — your password will not change.\n\n— CONFIT"
    )
    html = _layout(
        "Reset your password",
        "إعادة تعيين كلمة المرور",
        f"<p style='font-size:14px;line-height:1.7;'>Hello {_e(full_name or 'there')},</p>"
        f"<p style='font-size:14px;line-height:1.7;'>We received a request to reset your CONFIT password. "
        f"The link is valid for {int(ttl_minutes)} minutes and single use.</p>"
        f"{_button(reset_url, 'Reset my password')}"
        f"<p style='font-size:13px;color:#7A8095;'>If you did not request this, ignore this email — your password will not change.</p>",
        f"<p style='font-size:14px;line-height:1.7;'>وصلك طلب لإعادة تعيين كلمة المرور. الرابط صالح {int(ttl_minutes)} دقيقة وللاستخدام مرة واحدة.</p>"
        f"<p style='font-size:13px;color:#7A8095;'>إذا لم تطلب ذلك، تجاهل هذه الرسالة.</p>",
    )
    return subject, html, text


def render_password_changed_email(full_name: str, when: str, support_hint: str = "") -> tuple[str, str, str]:
    subject = _subject("Your CONFIT password was changed / تم تغيير كلمة المرور")
    text = (
        f"Hello {full_name},\n\n"
        f"Your CONFIT password was changed on {when}. All other sessions were signed out.\n"
        f"If this was not you, reset your password immediately and contact support.\n\n— CONFIT"
    )
    html = _layout(
        "Your password was changed",
        "تم تغيير كلمة المرور",
        f"<p style='font-size:14px;line-height:1.7;'>Hello {_e(full_name or 'there')},</p>"
        f"<p style='font-size:14px;line-height:1.7;'>Your password was changed on <strong>{_e(when)}</strong>. "
        f"All other sessions were signed out.</p>"
        f"<p style='font-size:13px;color:#7A8095;'>{_e(support_hint or 'If this was not you, reset your password immediately.')}</p>",
        f"<p style='font-size:14px;line-height:1.7;'>تم تغيير كلمة المرور بتاريخ {_e(when)}، وتم إنهاء الجلسات الأخرى.</p>"
        f"<p style='font-size:13px;color:#7A8095;'>إذا لم تكن أنت، أعد تعيين كلمة المرور فورًا.</p>",
    )
    return subject, html, text


# ---------------------------------------------------------------------------
# Email change
# ---------------------------------------------------------------------------

def render_email_change_verification_email(full_name: str, new_email: str, confirm_url: str) -> tuple[str, str, str]:
    subject = _subject("Confirm your new CONFIT email / تأكيد البريد الجديد")
    text = (
        f"Hello {full_name},\n\n"
        f"Confirm that {new_email} should become the address on your CONFIT account:\n{confirm_url}\n\n"
        f"The link is valid for 2 hours and can be used once. Your current address stays active until you confirm.\n\n— CONFIT"
    )
    html = _layout(
        "Confirm your new email address",
        "تأكيد البريد الإلكتروني الجديد",
        f"<p style='font-size:14px;line-height:1.7;'>Hello {_e(full_name or 'there')},</p>"
        f"<p style='font-size:14px;line-height:1.7;'>Confirm that <strong>{_e(new_email)}</strong> should become "
        f"the address on your CONFIT account. Your current address stays active until you confirm.</p>"
        f"{_button(confirm_url, 'Confirm new email')}",
        f"<p style='font-size:14px;line-height:1.7;'>أكّد أن البريد <strong>{_e(new_email)}</strong> سيصبح عنوان حسابك. "
        f"يبقى بريدك الحالي فعّالًا حتى التأكيد.</p>",
    )
    return subject, html, text


def render_email_changed_notice_email(full_name: str, old_email: str, new_email: str, when: str) -> tuple[str, str, str]:
    subject = _subject("Your CONFIT sign-in email changed / تم تغيير بريد الدخول")
    text = (
        f"Hello {full_name},\n\n"
        f"The sign-in email on your CONFIT account changed from {old_email} to {new_email} on {when}.\n"
        f"If this was not you, contact support immediately.\n\n— CONFIT"
    )
    html = _layout(
        "Your sign-in email changed",
        "تم تغيير بريد الدخول",
        f"<p style='font-size:14px;line-height:1.7;'>The sign-in email changed from <strong>{_e(old_email)}</strong> "
        f"to <strong>{_e(new_email)}</strong> on {_e(when)}.</p>"
        f"<p style='font-size:13px;color:#7A8095;'>If this was not you, contact support immediately.</p>",
        f"<p style='font-size:14px;line-height:1.7;'>تم تغيير بريد الدخول من {_e(old_email)} إلى {_e(new_email)} بتاريخ {_e(when)}.</p>",
    )
    return subject, html, text


# ---------------------------------------------------------------------------
# Partner lifecycle
# ---------------------------------------------------------------------------

def render_partner_invitation_email(
    invitee_name: str,
    brand_name: str,
    inviter_name: str,
    role_label: str,
    accept_url: str,
    expires_hours: int,
) -> tuple[str, str, str]:
    subject = _subject(f"{inviter_name} invited you to {brand_name} on CONFIT / دعوة للانضمام")
    text = (
        f"Hello {invitee_name or 'there'},\n\n"
        f"{inviter_name} invited you to join the {brand_name} partner workspace on CONFIT "
        f"as {role_label}. The invitation is valid for {expires_hours} hours and can be accepted once:\n"
        f"{accept_url}\n\n"
        f"If you were not expecting this, you can ignore this email.\n\n— CONFIT"
    )
    html = _layout(
        "You have been invited to a brand workspace",
        "دعوة للانضمام إلى مساحة علامة تجارية",
        f"<p style='font-size:14px;line-height:1.7;'>{_e(inviter_name)} invited you to join the "
        f"<strong>{_e(brand_name)}</strong> partner workspace as <strong>{_e(role_label)}</strong>.</p>"
        f"<p style='font-size:14px;line-height:1.7;'>The invitation is valid for {int(expires_hours)} hours and can be accepted once.</p>"
        f"{_button(accept_url, 'Accept invitation')}",
        f"<p style='font-size:14px;line-height:1.7;'>دعاك {_e(inviter_name)} للانضمام إلى مساحة "
        f"<strong>{_e(brand_name)}</strong> بصفة <strong>{_e(role_label)}</strong>. الدعوة صالحة {int(expires_hours)} ساعة.</p>",
    )
    return subject, html, text


def render_partner_application_received_email(full_name: str, brand_name: str) -> tuple[str, str, str]:
    subject = _subject("We received your CONFIT partner application / استلمنا طلبك")
    text = (
        f"Hello {full_name},\n\n"
        f"Your partner application for {brand_name} is now in review by the CONFIT platform team. "
        f"We will email you as soon as a decision is made. No brand portal access exists yet — "
        f"this is expected while the review is pending.\n\n— CONFIT"
    )
    html = _layout(
        "Your partner application is in review",
        "طلبك قيد المراجعة",
        f"<p style='font-size:14px;line-height:1.7;'>Thanks {_e(full_name or '')} — your application for "
        f"<strong>{_e(brand_name)}</strong> is now with the CONFIT platform team for review.</p>"
        f"<p style='font-size:14px;line-height:1.7;'>We will email you when a decision is recorded. "
        f"Until then your account keeps working as a shopper.</p>",
        f"<p style='font-size:14px;line-height:1.7;'>شكرًا لك، طلبك لـ <strong>{_e(brand_name)}</strong> قيد المراجعة من فريق منصة كونفيت.</p>",
    )
    return subject, html, text


def render_partner_application_decision_email(
    full_name: str,
    brand_name: str,
    approved: bool,
    note: str,
    portal_url: str,
) -> tuple[str, str, str]:
    if approved:
        subject = _subject("Your CONFIT partner account is approved / تمت الموافقة")
        text = (
            f"Hello {full_name},\n\n"
            f"Your partner application for {brand_name} was approved. You can now open the brand portal:\n"
            f"{portal_url}\n\n"
            f"Your account role is brand_owner for {brand_name}.\n\n— CONFIT"
        )
        html = _layout(
            "Your partner account is approved",
            "تمت الموافقة على حساب الشريك",
            f"<p style='font-size:14px;line-height:1.7;'>Your application for <strong>{_e(brand_name)}</strong> was approved. "
            f"Your account is now the owner of the {_e(brand_name)} workspace.</p>"
            f"{_button(portal_url, 'Open the brand portal')}",
            f"<p style='font-size:14px;line-height:1.7;'>تمت الموافقة على طلبك لـ <strong>{_e(brand_name)}</strong>. يمكنك الآن الدخول إلى بوابة العلامة.</p>",
        )
        return subject, html, text

    subject = _subject("Update on your CONFIT partner application / تحديث بخصوص طلبك")
    text = (
        f"Hello {full_name},\n\n"
        f"Your partner application for {brand_name} was not approved at this time.\n"
        f"{('Reviewer note: ' + note) if note else ''}\n"
        f"You may submit a new application with updated details at any time.\n\n— CONFIT"
    )
    html = _layout(
        "Update on your partner application",
        "تحديث بخصوص طلب الشراكة",
        f"<p style='font-size:14px;line-height:1.7;'>Your application for <strong>{_e(brand_name)}</strong> "
        f"was not approved at this time.</p>"
        f"{'<p style=&quot;font-size:14px;line-height:1.7;&quot;>Reviewer note: ' + _e(note) + '</p>' if note else ''}"
        f"<p style='font-size:14px;line-height:1.7;'>You may submit a new application with updated details at any time.</p>",
        f"<p style='font-size:14px;line-height:1.7;'>لم تتم الموافقة على طلبك لـ <strong>{_e(brand_name)}</strong> في الوقت الحالي، ويمكنك التقديم مرة أخرى ببيانات محدثة.</p>",
    )
    return subject, html, text


# ---------------------------------------------------------------------------
# Security notifications
# ---------------------------------------------------------------------------

def render_security_notification_email(full_name: str, event: str, detail: str, when: str) -> tuple[str, str, str]:
    subject = _subject(f"CONFIT security notice: {event} / تنبيه أمني")
    text = f"Hello {full_name},\n\n{event}\n{detail}\nWhen: {when}\n\nIf this was not you, secure your account.\n\n— CONFIT"
    html = _layout(
        "Security notice",
        "تنبيه أمني",
        f"<p style='font-size:14px;line-height:1.7;'><strong>{_e(event)}</strong></p>"
        f"<p style='font-size:14px;line-height:1.7;'>{_e(detail)}</p>"
        f"<p style='font-size:13px;color:#7A8095;'>When: {_e(when)}</p>",
        f"<p style='font-size:14px;line-height:1.7;'>{_e(event)}</p><p style='font-size:14px;line-height:1.7;'>{_e(detail)}</p>",
    )
    return subject, html, text
