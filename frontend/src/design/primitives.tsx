import {
  useEffect,
  useRef,
  useState,
  type HTMLAttributes,
  type ReactNode,
  type RefObject,
} from 'react';
import { Modal } from 'antd';

type ShellWidth = 'reading' | 'management' | 'full';

export interface AppShellProps extends HTMLAttributes<HTMLElement> {
  width?: ShellWidth;
  as?: 'main' | 'section' | 'div';
}

export function AppShell({
  width = 'management',
  as: Component = 'main',
  className = '',
  ...props
}: AppShellProps) {
  return (
    <Component
      className={`kp-app-shell kp-app-shell--${width} ${className}`.trim()}
      {...props}
    />
  );
}

export interface PageHeaderProps extends Omit<HTMLAttributes<HTMLElement>, 'title'> {
  title: ReactNode;
  eyebrow?: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
}

export function PageHeader({
  title,
  eyebrow,
  description,
  actions,
  className = '',
  ...props
}: PageHeaderProps) {
  return (
    <header className={`kp-page-header ${className}`.trim()} {...props}>
      <div className="kp-page-header__copy">
        {eyebrow ? <div className="kp-page-header__eyebrow">{eyebrow}</div> : null}
        <h1 className="kp-page-header__title">{title}</h1>
        {description ? <div className="kp-page-header__description">{description}</div> : null}
      </div>
      {actions ? <div className="kp-page-header__actions">{actions}</div> : null}
    </header>
  );
}

export interface SurfaceProps extends HTMLAttributes<HTMLElement> {
  as?: 'div' | 'section' | 'article';
  tone?: 'paper' | 'subtle' | 'elevated';
}

export function Surface({
  as: Component = 'div',
  tone = 'paper',
  className = '',
  ...props
}: SurfaceProps) {
  return (
    <Component
      className={`kp-surface kp-surface--${tone} ${className}`.trim()}
      {...props}
    />
  );
}

export interface EmptyStateProps extends Omit<HTMLAttributes<HTMLDivElement>, 'title'> {
  title: ReactNode;
  body?: ReactNode;
  action?: ReactNode;
  icon?: ReactNode;
  iconLabel?: string;
}

export function EmptyState({
  title,
  body,
  action,
  icon,
  iconLabel,
  className = '',
  ...props
}: EmptyStateProps) {
  return (
    <div className={`kp-empty-state ${className}`.trim()} {...props}>
      {icon ? (
        <div className="kp-empty-state__icon" aria-hidden={iconLabel ? undefined : true} aria-label={iconLabel}>
          {icon}
        </div>
      ) : null}
      <h2 className="kp-empty-state__title">{title}</h2>
      {body ? <div className="kp-empty-state__body">{body}</div> : null}
      {action ? <div className="kp-empty-state__action">{action}</div> : null}
    </div>
  );
}

export interface StatCardProps extends HTMLAttributes<HTMLDivElement> {
  label: ReactNode;
  value: ReactNode;
  /** Optional CSS color for the value (e.g. var(--color-success)). */
  valueColor?: string;
}

/** Dark/i18n/Layout spec §C: shared metric card — uppercase label + serif value.
 *  Replaces the inline stat-card markup previously duplicated across
 *  AdminDashboardPage / AdminQualityPage / ScopedMetricsPage. */
export function StatCard({ label, value, valueColor, className = '', ...props }: StatCardProps) {
  return (
    <div className={`kp-surface kp-surface--paper kp-stat-card glass-panel ${className}`.trim()} {...props}>
      <div className="kp-stat-card__label">{label}</div>
      <div className="kp-stat-card__value" style={valueColor ? { color: valueColor } : undefined}>{value}</div>
    </div>
  );
}

export interface StatusProps extends HTMLAttributes<HTMLSpanElement> {
  tone?: 'neutral' | 'info' | 'success' | 'warning' | 'error';
}

export function Status({ tone = 'neutral', className = '', children, ...props }: StatusProps) {
  return (
    <span className={`kp-status kp-status--${tone} ${className}`.trim()} data-tone={tone} {...props}>
      <span className="kp-status__mark" aria-hidden="true" />
      <span>{children}</span>
    </span>
  );
}

export interface ActionBarProps extends HTMLAttributes<HTMLDivElement> {
  primary?: ReactNode;
  secondary?: ReactNode;
  destructive?: ReactNode;
}

export function ActionBar({
  primary,
  secondary,
  destructive,
  className = '',
  ...props
}: ActionBarProps) {
  return (
    <div className={`kp-action-bar ${className}`.trim()} {...props}>
      <div className="kp-action-bar__secondary">{secondary}{destructive}</div>
      <div className="kp-action-bar__primary">{primary}</div>
    </div>
  );
}

export interface ConfirmDialogProps {
  open: boolean;
  title: ReactNode;
  description: ReactNode;
  confirmLabel: string;
  cancelLabel: string;
  destructive?: boolean;
  onConfirm: () => void | Promise<void>;
  onCancel: () => void;
  returnFocusRef?: RefObject<HTMLElement>;
}

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel,
  cancelLabel,
  destructive = false,
  onConfirm,
  onCancel,
  returnFocusRef,
}: ConfirmDialogProps) {
  const [pending, setPending] = useState(false);
  const wasOpen = useRef(open);

  useEffect(() => {
    if (wasOpen.current && !open) returnFocusRef?.current?.focus();
    wasOpen.current = open;
  }, [open, returnFocusRef]);

  const confirm = async () => {
    if (pending) return;
    setPending(true);
    try {
      await onConfirm();
    } finally {
      setPending(false);
    }
  };

  return (
    <Modal
      open={open}
      title={title}
      onOk={confirm}
      onCancel={pending ? undefined : onCancel}
      okText={confirmLabel}
      cancelText={cancelLabel}
      confirmLoading={pending}
      okButtonProps={{ danger: destructive, disabled: pending }}
      cancelButtonProps={{ disabled: pending }}
      centered
      destroyOnHidden
    >
      <div className="kp-confirm-dialog__description">{description}</div>
    </Modal>
  );
}
