import React from 'react'
import ReactDOM from 'react-dom/client'
import { AuthProvider } from "react-oidc-context"
import { isOidcConfigured, isProviderSurface, oidcConfig } from './authConfig'
import App from './App.tsx'
import { ProviderApp } from './ProviderApp.tsx'
import { ApplicationErrorBoundary } from './components/ApplicationErrorBoundary.tsx'
import './index.css'

const oidcConfigurationMessage = isProviderSurface
  ? 'Provider sign-in is not configured. Set the approved provider OIDC authority and client identifier before using this workspace.'
  : 'Institutional sign-in is not configured. Set the approved OIDC authority and client identifier before using this workspace.';

const application = (
  <ApplicationErrorBoundary>
    {isProviderSurface ? <ProviderApp /> : <App />}
  </ApplicationErrorBoundary>
);

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    {isOidcConfigured && oidcConfig ? (
      <AuthProvider {...oidcConfig}>{application}</AuthProvider>
    ) : (
      <main className="min-h-screen bg-white px-4 py-8 sm:px-8">
        <div role="alert" className="mx-auto max-w-5xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800">
          {oidcConfigurationMessage}
        </div>
      </main>
    )}
  </React.StrictMode>,
)
