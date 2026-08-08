import type { AuthProviderProps } from "react-oidc-context";

export const isProviderSurface = import.meta.env.VITE_APP_SURFACE === 'provider';
const authority = (isProviderSurface ? import.meta.env.VITE_PROVIDER_OIDC_AUTHORITY : import.meta.env.VITE_OIDC_AUTHORITY)?.trim();
const clientId = (isProviderSurface ? import.meta.env.VITE_PROVIDER_OIDC_CLIENT_ID : import.meta.env.VITE_OIDC_CLIENT_ID)?.trim();
const scope = (isProviderSurface ? import.meta.env.VITE_PROVIDER_OIDC_SCOPE : import.meta.env.VITE_OIDC_SCOPE)?.trim();
const audience = (isProviderSurface ? import.meta.env.VITE_PROVIDER_OIDC_AUDIENCE : import.meta.env.VITE_OIDC_AUDIENCE)?.trim();

export const isOidcConfigured = Boolean(authority && clientId);

export const oidcConfig: AuthProviderProps | null = isOidcConfigured ? {
  authority,
  client_id: clientId,
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
} : null;
