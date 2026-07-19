/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

import { Component, type ErrorInfo, type ReactNode } from 'react';
import { ReloadOutlined } from '@ant-design/icons';

interface Props {
  children: ReactNode;
  title: string;
  description: string;
  retryText: string;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

/**
 * ErrorBoundary (P0-3) — catches uncaught React errors and shows a friendly
 * fallback UI with a retry button instead of a blank white screen.
 *
 * V4.2 UI-V4.2-010: Retry now resets component state to re-mount the failed
 * subtree instead of calling window.location.reload(). Previously, reload()
 * killed all Zustand state, disconnected SSE/WebSocket, and reset the entire
 * SPA — losing unsaved chat content and login state. Now, retry only re-mounts
 * the failed subtree while preserving global app state.
 * [Source: V4.2/ui_ux/ui_bug_list_V4.2.md §UI-V4.2-010]
 */
export default class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('[ErrorBoundary] Caught error:', error, errorInfo);
  }

  // V4.2 UI-V4.2-010: Sub-tree re-mount instead of full-page reload.
  // Resetting hasError to false causes React to re-render children,
  // effectively re-mounting the failed sub-tree while preserving
  // all parent-level state (Zustand stores, auth, SSE connections).
  handleRetry = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className="section-enter" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '64px 24px', textAlign: 'center', height: '100%', minHeight: 300 }}>
          <div className="ambient-glow" style={{ width: 64, height: 64, borderRadius: 16, background: 'var(--color-error, #ff4d4f)', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 32, fontFamily: 'var(--font-family-serif)', marginBottom: 24 }}>!</div>
          <h2 style={{ fontSize: 20, fontWeight: 600, color: 'var(--color-text)', marginBottom: 8, letterSpacing: '-0.01em' }}>{this.props.title}</h2>
          <p style={{ fontSize: 15, color: 'var(--color-text-secondary)', marginBottom: 24, maxWidth: 400 }}>{this.props.description}</p>
          <button
            type="button"
            onClick={this.handleRetry}
            className="hover-lift btn-press primary-btn"
            style={{ borderRadius: 8, minHeight: 40, padding: '0 24px' }}
          >
            <ReloadOutlined aria-hidden="true" /> {this.props.retryText}
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
