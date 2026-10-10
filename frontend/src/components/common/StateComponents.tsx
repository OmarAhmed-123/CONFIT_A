import React from 'react';
import { useTranslation } from 'react-i18next';
import { AlertTriangle, Inbox, Loader2, RefreshCw } from 'lucide-react';
import { StatusIcon } from './InteractionPrimitives';
import { AccessibleButton } from './AccessiblePrimitives';

/**
 * StateComponents — consistent empty/loading/error states (FR-005, SC-005).
 *
 * WHY: CUS-22, BRD-12, ADM-18 found empty/error/loading states uneven across
 * consumer views, brand/admin dashboards static, order status timeline not live (CUS-21).
 *
 * These components provide:
 * - Consistent visual language (icon shape + text, never color alone)
 * - Accessible roles (status, alert, aria-live)
 * - Honest states (no fake success)
 * - Live status support (aria-live polite for updates)
 */

interface EmptyStateProps {
  title: string;
  description?: string;
  action?: { label: string; onClick: () => void };
  icon?: React.ReactNode;
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  title,
  description,
  action,
  icon,
}) => {
  const { t } = useTranslation();
  return (
    <div
      className="flex flex-col items-center justify-center py-16 px-6 text-center"
      role="status"
      aria-live="polite"
    >
      <div className="mb-4 rounded-full bg-slate-100 p-4">
        {icon ?? <Inbox size={24} aria-hidden="true" className="text-slate-400" />}
      </div>
      <h3 className="text-lg font-semibold text-[#1B1F3B] mb-1">{title}</h3>
      {description && <p className="text-sm text-slate-500 max-w-sm mb-4">{description}</p>}
      {action && (
        <AccessibleButton variant="primary" onClick={action.onClick}>
          {action.label}
        </AccessibleButton>
      )}
    </div>
  );
};

interface LoadingStateProps {
  label?: string;
  fullPage?: boolean;
}

export const LoadingState: React.FC<LoadingStateProps> = ({
  label,
  fullPage = false,
}) => {
  const { t } = useTranslation();
  const loadingLabel = label ?? t('common.loading', 'Loading...');

  return (
    <div
      className={`flex flex-col items-center justify-center ${fullPage ? 'min-h-[60vh]' : 'py-12'} px-6`}
      role="status"
      aria-live="polite"
      aria-busy="true"
    >
      <Loader2 size={24} aria-hidden="true" className="motion-safe:animate-spin text-[#C5A059] mb-3" />
      <p className="text-sm text-slate-600">{loadingLabel}</p>
      <span className="sr-only">{loadingLabel}</span>
    </div>
  );
};

interface ErrorStateProps {
  title?: string;
  message: string;
  retry?: { label: string; onClick: () => void };
  details?: string;
}

export const ErrorState: React.FC<ErrorStateProps> = ({
  title,
  message,
  retry,
  details,
}) => {
  const { t } = useTranslation();
  const errorTitle = title ?? t('common.error');

  return (
    <div className="flex flex-col items-center justify-center py-12 px-6 text-center" role="alert" aria-live="assertive">
      <div className="mb-4 rounded-full bg-rose-50 p-4">
        <AlertTriangle size={24} aria-hidden="true" className="text-rose-500" />
      </div>
      <h3 className="text-lg font-semibold text-[#1B1F3B] mb-1">{errorTitle}</h3>
      <p className="text-sm text-slate-600 max-w-sm mb-2">{message}</p>
      {details && <p className="text-xs text-slate-500 max-w-sm mb-4">{details}</p>}
      {retry && (
        <AccessibleButton variant="secondary" onClick={retry.onClick}>
          <RefreshCw size={16} aria-hidden="true" className="mr-2" />
          {retry.label}
        </AccessibleButton>
      )}
    </div>
  );
};

interface LiveStatusProps {
  status: 'idle' | 'loading' | 'success' | 'error';
  message: string;
  live?: boolean;
}

export const LiveStatus: React.FC<LiveStatusProps> = ({
  status,
  message,
  live = true,
}) => {
  const { t } = useTranslation();
  // CUS-21: order status timeline not live — this component provides live updates
  return (
    <div
      className="flex items-center gap-2 text-sm"
      role={status === 'error' ? 'alert' : 'status'}
      aria-live={live ? 'polite' : 'off'}
      aria-atomic="true"
    >
      <StatusIcon
        status={status === 'idle' ? 'info' : status}
        size={16}
        aria-hidden={false}
        label={status}
      />
      <span className="text-slate-700">{message}</span>
      {live && status === 'loading' && (
        <span className="sr-only">{t('common.live_updating')}</span>
      )}
    </div>
  );
};

interface ConfirmationDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: 'danger' | 'primary';
  isLoading?: boolean;
}

export const ConfirmationDialog: React.FC<ConfirmationDialogProps> = ({
  isOpen,
  onClose,
  onConfirm,
  title,
  message,
  confirmLabel,
  cancelLabel,
  variant = 'primary',
  isLoading = false,
}) => {
  const { t } = useTranslation();
  const confirmText = confirmLabel ?? t('common.confirm', 'Confirm');
  const cancelText = cancelLabel ?? t('common.cancel', 'Cancel');

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/75 backdrop-blur-md">
      <div
        className="w-full max-w-md bg-white rounded-3xl shadow-2xl border border-slate-200 overflow-hidden"
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-title"
        aria-describedby="confirm-message"
      >
        <div className="px-6 py-5">
          <h3 id="confirm-title" className="font-serif text-lg font-bold text-[#1B1F3B] mb-2">
            {title}
          </h3>
          <p id="confirm-message" className="text-sm text-slate-600">
            {message}
          </p>
        </div>
        <div className="flex items-center justify-end gap-3 px-6 py-4 bg-slate-50 border-t border-slate-100">
          <AccessibleButton variant="ghost" onClick={onClose} disabled={isLoading}>
            {cancelText}
          </AccessibleButton>
          <AccessibleButton
            variant={variant === 'danger' ? 'danger' : 'primary'}
            onClick={onConfirm}
            isLoading={isLoading}
          >
            {confirmText}
          </AccessibleButton>
        </div>
      </div>
    </div>
  );
};
