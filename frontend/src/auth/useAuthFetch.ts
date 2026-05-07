import { useMsal } from '@azure/msal-react'
import { loginRequest } from './msalConfig'

// Wraps fetch with a silently-acquired Microsoft id_token.
// Falls back to unauthenticated fetch when MSAL has no active account
// (dev mode — no VITE_AZURE_CLIENT_ID configured).
export function useAuthFetch() {
  const { instance, accounts } = useMsal()

  return async function authFetch(url: string, options: RequestInit = {}): Promise<Response> {
    const account = accounts[0]
    if (!account) {
      return fetch(url, options)
    }

    const token = await instance.acquireTokenSilent({ ...loginRequest, account })

    return fetch(url, {
      ...options,
      headers: {
        ...(options.headers ?? {}),
        Authorization: `Bearer ${token.idToken}`,
      },
    })
  }
}
