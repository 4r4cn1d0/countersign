const storageKey = "agent_observer_token";

export function getStoredAuthToken(): string | null {
  const urlToken = new URLSearchParams(window.location.search).get("token");
  if (urlToken) {
    window.localStorage.setItem(storageKey, urlToken);
    return urlToken;
  }
  return window.localStorage.getItem(storageKey);
}

export function clearStoredAuthToken(): void {
  window.localStorage.removeItem(storageKey);
}
