import type { AuthProviderProps } from "react-oidc-context";

export const isProviderSurface = import.meta.env.VITE_APP_SURFACE === 'provider';
const authority = isProviderSurface ? import.meta.env.VITE_PROVIDER_OIDC_AUTHORITY : import.meta.env.VITE_OIDC_AUTHORITY;
const clientId = isProviderSurface ? import.meta.env.VITE_PROVIDER_OIDC_CLIENT_ID : import.meta.env.VITE_OIDC_CLIENT_ID;
const scope = isProviderSurface ? import.meta.env.VITE_PROVIDER_OIDC_SCOPE : import.meta.env.VITE_OIDC_SCOPE;
const audience = isProviderSurface ? import.meta.env.VITE_PROVIDER_OIDC_AUDIENCE : import.meta.env.VITE_OIDC_AUDIENCE;

export const isOidcConfigured = Boolean(authority && clientId);

export const oidcConfig: AuthProviderProps = {
  authority: authority || "https://your-tenant.auth0.com",
  client_id: clientId || "your-client-id",
  redirect_uri: window.location.origin,
  post_logout_redirect_uri: window.location.origin,
  response_type: "code",
  scope: scope || "openid profile email",
  ...(audience
    ? { extraQueryParams: { audience } }
    : {}),
  onSigninCallback: (_user: any | void): void => {
    window.history.replaceState(
      {},
      document.title,
      window.location.pathname
    );
  }
};
