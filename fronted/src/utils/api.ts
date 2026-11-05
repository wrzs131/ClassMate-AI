/** 学生端接口封装：uni.request + token 持久化，H5 / 小程序同源。 */
const BASE_KEY = "classmate_api_base";
const TOKEN_KEY = "classmate_token";
const USER_KEY = "classmate_user";
const SESSION_KEY = "classmate_session"; // 旧版全局缓存，仅用于清理
const SESSION_KEY_PREFIX = "classmate_joined_"; // 新版按账号分开存

export const DEFAULT_BASE = "http://127.0.0.1:8001/api";

export function apiBase(): string {
  return (uni.getStorageSync(BASE_KEY) as string) || DEFAULT_BASE;
}

export function setApiBase(base: string) {
  uni.setStorageSync(BASE_KEY, base.replace(/\/$/, ""));
}

export function getToken(): string {
  return (uni.getStorageSync(TOKEN_KEY) as string) || "";
}

export function setToken(token: string) {
  uni.setStorageSync(TOKEN_KEY, token || "");
}

export function getUser(): any {
  const raw = uni.getStorageSync(USER_KEY);
  if (!raw) return null;
  try {
    return typeof raw === "string" ? JSON.parse(raw) : raw;
  } catch {
    return null;
  }
}

export function setUser(user: any) {
  uni.setStorageSync(USER_KEY, JSON.stringify(user || {}));
}

export function clearAuth() {
  uni.removeStorageSync(TOKEN_KEY);
  uni.removeStorageSync(USER_KEY);
}

export interface JoinedSession {
  id: string;
  class_code: string;
  lesson_title?: string;
  student_id?: string;
}

/** 「加入的课堂」按账号分开存：切账号不会串号，退出登录也不会把自己的课堂记录删掉。 */
function currentUserId(): string {
  return String(getUser()?.id || "guest");
}

function joinedKey(): string {
  return `${SESSION_KEY_PREFIX}${currentUserId()}`;
}

export function getJoined(): JoinedSession | null {
  const raw = uni.getStorageSync(joinedKey());
  if (!raw) return null;
  try {
    const parsed = typeof raw === "string" ? JSON.parse(raw) : raw;
    return parsed?.id ? parsed : null;
  } catch {
    return null;
  }
}

export function setJoined(session: JoinedSession | null) {
  // 旧版是全局单条缓存（classmate_session），切账号会把别人的课堂带过来，这里顺手清掉
  uni.removeStorageSync(SESSION_KEY);
  const key = joinedKey();
  if (session) {
    uni.setStorageSync(key, JSON.stringify({ ...session, student_id: currentUserId() }));
  } else {
    uni.removeStorageSync(key);
  }
}

export function request<T = any>(
  path: string,
  options: { method?: "GET" | "POST"; data?: any; timeout?: number } = {}
): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const token = getToken();
    uni.request({
      url: `${apiBase()}${path}`,
      method: options.method || "GET",
      data: options.data,
      // 默认 60s：AI 批改（多题打分 + 学情诊断）可能更久，需要单独放宽超时
      timeout: options.timeout || 60000,
      header: token ? { Authorization: `Bearer ${token}` } : {},
      success: (res) => {
        const status = res.statusCode || 0;
        const data: any = res.data;
        if (status >= 200 && status < 300) {
          resolve(data as T);
          return;
        }
        if (status === 401) {
          clearAuth();
          setTimeout(() => uni.reLaunch({ url: "/pages/login/login" }), 50);
        }
        const detail = (data && (data.detail || data.message)) || `请求失败（${status}）`;
        reject(new Error(typeof detail === "string" ? detail : JSON.stringify(detail)));
      },
      fail: (err) => reject(new Error(err.errMsg || "网络连接失败，请检查后端是否启动")),
    });
  });
}

export const api = {
  login: (username: string, password: string) =>
    request<{ token: string; user: any }>("/auth/login", { method: "POST", data: { username, password } }),
  register: (payload: { role: string; username: string; password: string; nickname: string }) =>
    request<{ token: string; user: any }>("/auth/register", { method: "POST", data: payload }),
  me: () => request("/auth/me"),

  join: (classCode: string) => request("/classroom/join", { method: "POST", data: { class_code: classCode } }),
  leave: (sessionId: string) => request(`/classroom/${sessionId}/leave`, { method: "POST" }),
  state: (sessionId: string) => request(`/classroom/${sessionId}/state`),
  ask: (sessionId: string, question: string, imageBase64?: string) =>
    request(`/classroom/${sessionId}/ask`, {
      method: "POST",
      data: { question, image_base64: imageBase64 || null },
    }),

  quiz: (quizId: string) => request(`/quiz/${quizId}`),
  submit: (quizId: string, answers: { item_id: string; answer: string }[]) =>
    request(`/quiz/${quizId}/submit`, { method: "POST", data: { answers }, timeout: 180000 }),
  report: (quizId: string) => request(`/quiz/${quizId}/report`),
  myDiagnosis: () => request("/me/diagnosis"),
};

/** 把图片转成纯 base64（用于 Qwen3-VL 识别手写步骤）。 */
export function readImageBase64(filePath: string): Promise<string> {
  return new Promise((resolve, reject) => {
    // #ifdef H5
    fetch(filePath)
      .then((res) => res.blob())
      .then((blob) => {
        const reader = new FileReader();
        reader.onload = () => {
          const text = String(reader.result || "");
          resolve(text.split(",")[1] || "");
        };
        reader.onerror = () => reject(new Error("图片读取失败"));
        reader.readAsDataURL(blob);
      })
      .catch(() => reject(new Error("图片读取失败")));
    return;
    // #endif
    // #ifndef H5
    uni.getFileSystemManager().readFile({
      filePath,
      encoding: "base64",
      success: (res) => resolve(res.data as string),
      fail: () => reject(new Error("图片读取失败")),
    });
    // #endif
  });
}

export function goLogin() {
  // 小程序端若在页面 onLoad/onShow 阶段立刻 reLaunch，刚挂载的自定义组件（uni-ui）还没完成
  // __l 关联就被销毁，微信基础库会抛 Cannot read property 'forceUpdate' of undefined。
  // 这里延后一拍，等当前页渲染/挂载结束后再跳转。
  setTimeout(() => {
    uni.reLaunch({ url: "/pages/login/login" });
  }, 0);
}

export function requireLogin() {
  if (!getToken()) {
    goLogin();
    return false;
  }
  return true;
}
