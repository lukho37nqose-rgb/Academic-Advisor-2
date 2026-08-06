import React from 'react'
import ReactDOM from 'react-dom/client'
import { AuthProvider } from "react-oidc-context"
import { oidcConfig } from './authConfig'
import App from './App.tsx'
import { ProviderApp } from './ProviderApp.tsx'
import { ApplicationErrorBoundary } from './components/ApplicationErrorBoundary.tsx'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <AuthProvider {...oidcConfig}>
      <ApplicationErrorBoundary>
        {import.meta.env.VITE_APP_SURFACE === 'provider' ? <ProviderApp /> : <App />}
      </ApplicationErrorBoundary>
    </AuthProvider>
  </React.StrictMode>,
)
