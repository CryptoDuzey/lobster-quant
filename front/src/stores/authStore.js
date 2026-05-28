import { reactive } from "vue";
import { login as loginApi, logout as logoutApi, me, register as registerApi } from "../api/authApi";

const state = reactive({
  token: localStorage.getItem("lobster_token") || "",
  user: JSON.parse(localStorage.getItem("lobster_user") || "null"),
  loading: false,
  error: null,
});

function persist(token, user) {
  state.token = token;
  state.user = user;
  localStorage.setItem("lobster_token", token);
  localStorage.setItem("lobster_user", JSON.stringify(user));
}

export function useAuthStore() {
  async function register(payload) {
    state.loading = true;
    state.error = null;
    try {
      const result = await registerApi(payload);
      persist(result.token, result.user);
      return result.user;
    } catch (error) {
      state.error = error.message;
      throw error;
    } finally {
      state.loading = false;
    }
  }

  async function login(payload) {
    state.loading = true;
    state.error = null;
    try {
      const result = await loginApi(payload);
      persist(result.token, result.user);
      return result.user;
    } catch (error) {
      state.error = error.message;
      throw error;
    } finally {
      state.loading = false;
    }
  }

  async function loadMe() {
    if (!state.token) return null;
    try {
      const result = await me();
      state.user = result.user;
      localStorage.setItem("lobster_user", JSON.stringify(result.user));
      return result.user;
    } catch {
      state.token = "";
      state.user = null;
      localStorage.removeItem("lobster_token");
      localStorage.removeItem("lobster_user");
      return null;
    }
  }

  async function logout() {
    try {
      await logoutApi();
    } finally {
      state.token = "";
      state.user = null;
      localStorage.removeItem("lobster_token");
      localStorage.removeItem("lobster_user");
    }
  }

  return { state, register, login, loadMe, logout };
}
