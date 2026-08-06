import { Component, type ErrorInfo, type ReactNode } from 'react';
import { AlertTriangle, RotateCcw } from 'lucide-react';

type Props = { children: ReactNode };
type State = { failed: boolean };

export class ApplicationErrorBoundary extends Component<Props, State> {
  state: State = { failed: false };

  static getDerivedStateFromError(): State {
    return { failed: true };
  }

  componentDidCatch(_error: Error, _info: ErrorInfo) {
    // The detailed error remains in the browser console for support staff;
    // the person using the service receives a safe, actionable recovery path.
  }

  render() {
    if (this.state.failed) {
      return <main className="flex min-h-screen items-center justify-center bg-white px-6 py-10"><section role="alert" className="max-w-lg border border-rose-200 bg-rose-50 p-6 text-rose-900"><AlertTriangle className="h-6 w-6" /><h1 className="mt-4 text-xl font-semibold">This page could not be displayed</h1><p className="mt-2 text-sm leading-relaxed">Your information has not been changed. Reload the page to try again. If this continues, contact your institution and describe what you were doing.</p><button type="button" onClick={() => window.location.reload()} className="mt-5 inline-flex items-center gap-2 rounded border border-rose-300 bg-white px-3 py-2 text-sm font-medium hover:bg-rose-100"><RotateCcw className="h-4 w-4" />Reload page</button></section></main>;
    }
    return this.props.children;
  }
}
