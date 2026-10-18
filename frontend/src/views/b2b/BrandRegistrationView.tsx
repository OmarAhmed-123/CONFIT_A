import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { brandService } from '../../services/apiServices';
import { useAuthStore } from '../../stores/authStore';
import { ConfitLogo } from '../../components/common/ConfitLogo';

export const BrandRegistrationView: React.FC = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const setSession = useAuthStore((s) => s.setSession);

  // Form inputs
  const [brandName, setBrandName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [fullName, setFullName] = useState('');
  const [phone, setPhone] = useState('');
  const [description, setDescription] = useState('');
  const [website, setWebsite] = useState('');
  const [city, setCity] = useState('Dubai');
  const [country, setCountry] = useState('UAE');

  // Submission state
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successResponse, setSuccessResponse] = useState<any | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (brandName.trim().length < 2) {
      setError(t('brand_reg.brand_name_placeholder'));
      return;
    }
    if (!email.includes('@') || !email.includes('.')) {
      setError(t('brand_reg.email_placeholder'));
      return;
    }
    if (password.length < 8) {
      setError(t('brand_reg.password_placeholder'));
      return;
    }
    if (fullName.trim().length < 2) {
      setError(t('brand_reg.full_name_placeholder'));
      return;
    }

    setIsSubmitting(true);
    try {
      const res = await brandService.registerBrand({
        brand_name: brandName.trim(),
        email: email.trim().toLowerCase(),
        password,
        full_name: fullName.trim(),
        phone: phone.trim() || undefined,
        description: description.trim() || undefined,
        website: website.trim() || undefined,
        city: city.trim(),
        country: country.trim(),
      });

      // Update auth session
      if (res.access_token) {
        const dummyUser = {
          id: res.brand.user_id,
          email: email.trim().toLowerCase(),
          full_name: fullName.trim(),
          role: 'brand_owner' as any,
          preferred_language: 'en',
          is_active: true,
          is_verified: false,
          mfa_enabled: false,
          created_at: new Date().toISOString(),
          has_profile: true,
          brand_id: res.brand.id,
        };
        setSession(res.access_token, res.refresh_token, dummyUser);
      }

      setSuccessResponse(res);
    } catch (err: any) {
      setError(err?.message || err?.detail || t('brand_reg.error_generic'));
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-white text-brand-charcoal font-sans pb-24">
      {/* Top Navbar Header */}
      <header className="border-b border-neutral-200 bg-white sticky top-0 z-30">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4 flex items-center justify-between">
          <Link to="/" className="inline-flex items-center gap-2">
            <ConfitLogo variant="compact" theme="dark" size="sm" />
          </Link>

          <div className="flex items-center gap-3">
            <Link
              to="/b2b"
              className="text-xs font-semibold text-neutral-600 hover:text-brand-charcoal transition-colors"
            >
              &larr; {t('brand_reg.back_to_b2b')}
            </Link>
          </div>
        </div>
      </header>

      <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 pt-10">
        {/* Success View */}
        {successResponse ? (
          <div className="rounded-3xl border border-neutral-200 p-8 sm:p-12 text-center bg-neutral-50 shadow-sm space-y-6">
            <div className="mx-auto h-16 w-16 rounded-full bg-emerald-100 border border-emerald-200 flex items-center justify-center text-emerald-700">
              <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
              </svg>
            </div>

            <div className="space-y-2">
              <span className="text-xs font-bold uppercase tracking-wider text-brand-coral">
                {successResponse.brand.brand_name}
              </span>
              <h2 className="font-serif text-3xl font-bold tracking-tight text-brand-charcoal">
                {t('brand_reg.success_title')}
              </h2>
              <p className="text-sm text-neutral-600 max-w-xl mx-auto leading-relaxed">
                {t('brand_reg.success_message')}
              </p>
            </div>

            <div className="p-4 rounded-2xl bg-white border border-neutral-200 text-xs text-left max-w-md mx-auto space-y-1.5">
              <div className="flex justify-between">
                <span className="text-neutral-500">Brand Identifier:</span>
                <span className="font-mono font-bold text-brand-charcoal">{successResponse.brand.slug}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-neutral-500">Moderation Status:</span>
                <span className="font-semibold text-amber-700 bg-amber-50 px-2 py-0.5 rounded border border-amber-200">
                  Awaiting Verification
                </span>
              </div>
            </div>

            <div className="flex flex-col sm:flex-row items-center justify-center gap-3 pt-2">
              <button data-motion="admin"
                type="button"
                onClick={() => navigate('/b2b/branches')}
                className="w-full sm:w-auto px-8 py-3.5 rounded-2xl bg-brand-charcoal text-white text-xs font-bold hover:bg-neutral-800 transition-colors shadow-sm"
              >
                {t('brand_reg.complete_setup_cta')} &rarr;
              </button>
              <button data-motion="admin"
                type="button"
                onClick={() => navigate('/b2b')}
                className="w-full sm:w-auto px-8 py-3.5 rounded-2xl border border-neutral-300 bg-white text-neutral-700 text-xs font-bold hover:bg-neutral-50 transition-colors"
              >
                {t('brand_reg.view_portal_cta')}
              </button>
            </div>
          </div>
        ) : (
          /* Registration Form View */
          <div className="space-y-8">
            <div className="space-y-2">
              <span className="text-xs font-bold uppercase tracking-widest text-brand-coral">
                Brand Partner Onboarding
              </span>
              <h1 className="font-serif text-3xl sm:text-4xl font-bold tracking-tight text-brand-charcoal">
                {t('brand_reg.title')}
              </h1>
              <p className="text-sm text-neutral-600 leading-relaxed">
                {t('brand_reg.subtitle')}
              </p>
            </div>

            {error && (
              <div className="rounded-2xl border border-red-200 bg-red-50 p-4 text-xs text-red-800 space-y-1">
                <p className="font-bold">{t('brand_reg.alert_title', 'Registration Alert')}</p>
                <p>{error}</p>
              </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-6">
              {/* Brand Core Information */}
              <div className="p-6 rounded-3xl bg-neutral-50 border border-neutral-200 space-y-4">
                <h3 className="font-serif text-base font-bold text-brand-charcoal">
                  1. Brand Identity
                </h3>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div className="sm:col-span-2">
                    <label className="block text-xs font-bold text-neutral-700 mb-1">
                      {t('brand_reg.brand_name_label')} *
                    </label>
                    <input
                      type="text"
                      name="brandName"
                      required
                      value={brandName}
                      onChange={(e) => setBrandName(e.target.value)}
                      placeholder={t('brand_reg.brand_name_placeholder')}
                      className="w-full rounded-xl bg-white border border-neutral-300 px-3.5 py-2.5 text-xs font-medium text-brand-charcoal placeholder-neutral-400 focus:outline-none focus:ring-2 focus:ring-brand-charcoal"
                    />
                  </div>

                  <div className="sm:col-span-2">
                    <label className="block text-xs font-bold text-neutral-700 mb-1">
                      {t('brand_reg.description_label')}
                    </label>
                    <textarea
                      rows={3}
                      name="description"
                      value={description}
                      onChange={(e) => setDescription(e.target.value)}
                      placeholder={t('brand_reg.description_placeholder')}
                      className="w-full rounded-xl bg-white border border-neutral-300 p-3.5 text-xs font-medium text-brand-charcoal placeholder-neutral-400 focus:outline-none focus:ring-2 focus:ring-brand-charcoal"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-bold text-neutral-700 mb-1">
                      {t('brand_reg.website_label')}
                    </label>
                    <input
                      type="url"
                      name="website"
                      value={website}
                      onChange={(e) => setWebsite(e.target.value)}
                      placeholder={t('brand_reg.website_placeholder')}
                      className="w-full rounded-xl bg-white border border-neutral-300 px-3.5 py-2.5 text-xs font-medium text-brand-charcoal placeholder-neutral-400 focus:outline-none focus:ring-2 focus:ring-brand-charcoal"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-bold text-neutral-700 mb-1">
                      {t('brand_reg.city_label')}
                    </label>
                    <input
                      type="text"
                      name="city"
                      value={city}
                      onChange={(e) => setCity(e.target.value)}
                      placeholder={t('brand_reg.city_placeholder')}
                      className="w-full rounded-xl bg-white border border-neutral-300 px-3.5 py-2.5 text-xs font-medium text-brand-charcoal placeholder-neutral-400 focus:outline-none focus:ring-2 focus:ring-brand-charcoal"
                    />
                  </div>
                </div>
              </div>

              {/* Authorized Owner Signatory */}
              <div className="p-6 rounded-3xl bg-neutral-50 border border-neutral-200 space-y-4">
                <h3 className="font-serif text-base font-bold text-brand-charcoal">
                  2. Authorized Signatory & Credentials
                </h3>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-bold text-neutral-700 mb-1">
                      {t('brand_reg.full_name_label')} *
                    </label>
                    <input
                      type="text"
                      name="fullName"
                      required
                      value={fullName}
                      onChange={(e) => setFullName(e.target.value)}
                      placeholder={t('brand_reg.full_name_placeholder')}
                      className="w-full rounded-xl bg-white border border-neutral-300 px-3.5 py-2.5 text-xs font-medium text-brand-charcoal placeholder-neutral-400 focus:outline-none focus:ring-2 focus:ring-brand-charcoal"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-bold text-neutral-700 mb-1">
                      {t('brand_reg.email_label')} *
                    </label>
                    <input
                      type="email"
                      name="email"
                      required
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder={t('brand_reg.email_placeholder')}
                      className="w-full rounded-xl bg-white border border-neutral-300 px-3.5 py-2.5 text-xs font-medium text-brand-charcoal placeholder-neutral-400 focus:outline-none focus:ring-2 focus:ring-brand-charcoal"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-bold text-neutral-700 mb-1">
                      {t('brand_reg.password_label')} *
                    </label>
                    <input
                      type="password"
                      name="password"
                      required
                      minLength={8}
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      placeholder={t('brand_reg.password_placeholder')}
                      className="w-full rounded-xl bg-white border border-neutral-300 px-3.5 py-2.5 text-xs font-medium text-brand-charcoal placeholder-neutral-400 focus:outline-none focus:ring-2 focus:ring-brand-charcoal"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-bold text-neutral-700 mb-1">
                      {t('brand_reg.phone_label')}
                    </label>
                    <input
                      type="tel"
                      name="phone"
                      value={phone}
                      onChange={(e) => setPhone(e.target.value)}
                      placeholder={t('brand_reg.phone_placeholder')}
                      className="w-full rounded-xl bg-white border border-neutral-300 px-3.5 py-2.5 text-xs font-medium text-brand-charcoal placeholder-neutral-400 focus:outline-none focus:ring-2 focus:ring-brand-charcoal"
                    />
                  </div>
                </div>
              </div>

              {/* Submit CTA */}
              <div className="pt-2 space-y-4">
                <button data-motion="auth" data-motion-tone="icon"
                  type="submit"
                  disabled={isSubmitting}
                  className="w-full py-4 rounded-2xl bg-brand-charcoal text-white text-xs font-bold hover:bg-neutral-800 disabled:opacity-50 transition-colors shadow-sm"
                >
                  {isSubmitting ? t('brand_reg.submitting') : t('brand_reg.submit_btn')}
                </button>

                <p className="text-center text-xs text-neutral-500">
                  {t('brand_reg.already_have_account')}{' '}
                  <Link to="/b2b" className="font-bold text-brand-charcoal hover:underline">
                    {t('brand_reg.sign_in_link')}
                  </Link>
                </p>
              </div>
            </form>
          </div>
        )}
      </div>
    </div>
  );
};
