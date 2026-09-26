import React from 'react';
import { useTranslation } from 'react-i18next';
import { useLocation, useNavigate } from 'react-router-dom';

interface BoundaryState {
  error: Error | null;
  retryKey: number;
}

interface BoundaryProps {
  children: React.ReactNode;
  renderFallback: (reset: () => void) => React.ReactNode;
}

/**
 * A route-local failure boundary for the unusually interactive try-on surface.
 * It does not claim a failed render succeeded: the exception is logged and the
 * customer gets explicit retry/navigation controls instead of an empty root.
 */
class TryOnRenderBoundary extends React.Component<BoundaryProps, BoundaryState> {
  state: BoundaryState = { error: null, retryKey: 0 };

  static getDerivedStateFromError(error: Error): Partial<BoundaryState> {
    return { error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error('Try-On Studio render failure', error, info.componentStack);
  }

  reset = () => {
    this.setState((state) => ({ error: null, retryKey: state.retryKey + 1 }));
  };

  render() {
    if (this.state.error) return this.props.renderFallback(this.reset);
    return <React.Fragment key={this.state.retryKey}>{this.props.children}</React.Fragment>;
  }
}

export const TryOnStudioErrorBoundary: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();

  const leaveStudio = () => {
    if (location.key && location.key !== 'default') {
      navigate(-1);
      return;
    }
    navigate('/', { replace: true });
  };

  return (
    <TryOnRenderBoundary
      renderFallback={(reset) => (
        <section
          role="alert"
          className="mx-auto my-12 max-w-2xl rounded-3xl border border-amber-200 bg-white p-6 text-center shadow-sm sm:p-10"
        >
          <span aria-hidden="true" className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-amber-50 text-xl">
            ⚠️
          </span>
          <h1 className="mt-4 font-serif text-2xl font-bold text-[#1B1F3B]">
            {t('tryon.studio_error_title')}
          </h1>
          <p className="mx-auto mt-2 max-w-lg text-sm leading-relaxed text-slate-600">
            {t('tryon.studio_error_detail')}
          </p>
          <div className="mt-6 flex flex-col justify-center gap-3 sm:flex-row">
            <button
              type="button"
              onClick={reset}
              className="min-h-11 rounded-xl bg-[#1B1F3B] px-5 py-2.5 text-sm font-bold text-white hover:bg-[#0C0E1E] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C5A059]"
            >
              {t('tryon.studio_error_retry')}
            </button>
            <button
              type="button"
              onClick={leaveStudio}
              className="min-h-11 rounded-xl border border-slate-300 bg-white px-5 py-2.5 text-sm font-semibold text-slate-700 hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C5A059]"
            >
              <span aria-hidden="true">{i18n.dir() === 'rtl' ? '→' : '←'} </span>
              {t('tryon.studio_error_back')}
            </button>
          </div>
        </section>
      )}
    >
      {children}
    </TryOnRenderBoundary>
  );
};
