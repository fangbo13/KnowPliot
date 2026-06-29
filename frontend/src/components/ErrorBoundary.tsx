import { Component, type ErrorInfo, type ReactNode } from 'react';
import { Button, Result } from 'antd';
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
        <Result
          status="error"
          title={this.props.title}
          subTitle={this.props.description}
          extra={
            <Button
              type="primary"
              icon={<ReloadOutlined />}
              onClick={this.handleRetry}
            >
              {this.props.retryText}
            </Button>
          }
        />
      );
    }
    return this.props.children;
  }
}
