import { reactive } from "vue";
import { pushToast } from "./useToast";

const state = reactive({
  token: localStorage.getItem("auth_token") || "",
  user: null,
  ready: false,
  loginOpen: false,
});


function persistSession(token, user) {
  state.token = token;
  state.user = user;
  localStorage.setItem("auth_token", token);
}


export function useAuthStore() {
  return state;
}


export function getAccessToken() {
  return state.token;
}


export function openLogin() {
  state.loginOpen = true;
}


export function closeLogin() {
  state.loginOpen = false;
}


export function clearAuth() {
  state.token = "";
  state.user = null;
  localStorage.removeItem("auth_token");
}


export async function loginWithPassword(username, password) {
  const response = await fetch("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || "登录失败");
  }
  const payload = await response.json();
  persistSession(payload.accessToken, payload.user);
  state.loginOpen = false;
  pushToast(`欢迎回来，${payload.user.username}`);
  return payload.user;
}


export async function restoreAuth() {
  if (!state.token) {
    state.ready = true;
    return;
  }
  try {
    const response = await fetch("/api/auth/me", {
      headers: { Authorization: `Bearer ${state.token}` },
    });
    if (!response.ok) {
      throw new Error("auth-expired");
    }
    state.user = await response.json();
  } catch (_) {
    clearAuth();
  } finally {
    state.ready = true;
  }
}


export function logout() {
  const username = state.user?.username;
  clearAuth();
  pushToast(username ? `${username} 已退出登录` : "已退出登录");
}
