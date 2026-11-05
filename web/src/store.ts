import { reactive } from "vue";
import { api, getToken, setToken } from "./api";

interface AppState {
  user: any | null;
  health: any | null;
  booting: boolean;
  lesson: any | null;
  lessonId: string;
  sessionId: string;
}

export const state = reactive<AppState>({
  user: null,
  health: null,
  booting: true,
  lesson: null,
  lessonId: localStorage.getItem("classmate_lesson") || "",
  sessionId: localStorage.getItem("classmate_session") || "",
});

export async function boot() {
  try {
    state.health = await api.health();
  } catch {
    state.health = null;
  }
  if (getToken()) {
    try {
      state.user = await api.me();
    } catch {
      setToken("");
      state.user = null;
    }
  }
  state.booting = false;
}

export async function login(username: string, password: string) {
  const data = await api.login(username, password);
  setToken(data.token);
  state.user = data.user;
  // 换账号登录：上一个账号缓存的课堂 id 不再属于当前用户，必须清掉，
  // 否则授课控制台/学情诊断会自动打开别人的课堂并返回 403「无权访问」
  rememberSession("");
}

export async function register(payload: { role: string; username: string; password: string; nickname: string }) {
  const data = await api.register(payload);
  setToken(data.token);
  state.user = data.user;
  rememberSession("");
}

export function logout() {
  setToken("");
  state.user = null;
  rememberSession("");
}

export function rememberLesson(id: string) {
  state.lessonId = id;
  if (id) localStorage.setItem("classmate_lesson", id);
  else localStorage.removeItem("classmate_lesson");
}

export function rememberSession(id: string) {
  state.sessionId = id;
  if (id) localStorage.setItem("classmate_session", id);
  else localStorage.removeItem("classmate_session");
}
