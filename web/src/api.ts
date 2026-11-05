/** 后端接口封装：统一 token、错误处理与 API 地址。 */
const TOKEN_KEY = "classmate_token";
const BASE_KEY = "classmate_api_base";

export function getApiBase(): string {
  return localStorage.getItem(BASE_KEY) || import.meta.env.VITE_API_BASE || "/api";
}

export function setApiBase(base: string) {
  localStorage.setItem(BASE_KEY, base.replace(/\/$/, ""));
}

export function getToken(): string {
  return localStorage.getItem(TOKEN_KEY) || "";
}

export function setToken(token: string) {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function request<T = any>(path: string, options: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = { ...(options.headers as Record<string, string>) };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  if (options.body && !(options.body instanceof FormData)) headers["Content-Type"] = "application/json";

  const res = await fetch(`${getApiBase()}${path}`, { ...options, headers });
  const text = await res.text();
  let data: any = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }
  if (!res.ok) {
    const detail = (data && (data.detail || data.message)) || `请求失败（${res.status}）`;
    throw new ApiError(typeof detail === "string" ? detail : JSON.stringify(detail), res.status);
  }
  return data as T;
}

export const api = {
  health: () => request("/health"),

  login: (username: string, password: string) =>
    request<{ token: string; user: any }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  register: (payload: { role: string; username: string; password: string; nickname: string }) =>
    request<{ token: string; user: any }>("/auth/register", { method: "POST", body: JSON.stringify(payload) }),
  me: () => request("/auth/me"),

  listLessons: () => request<{ lessons: any[] }>("/courseware"),
  getLesson: (id: string) => request(`/courseware/${id}`),
  generate: (payload: any) => request("/courseware/generate", { method: "POST", body: JSON.stringify(payload) }),
  patchSlide: (lessonId: string, slideId: string, payload: any) =>
    request(`/courseware/${lessonId}/slides/${slideId}`, { method: "PATCH", body: JSON.stringify(payload) }),
  exportLesson: async (lessonId: string, format: "pptx" | "json") => {
    const token = getToken();
    const res = await fetch(`${getApiBase()}/courseware/${lessonId}/export`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify({ format }),
    });
    if (!res.ok) throw new ApiError(`导出失败（${res.status}）`, res.status);
    return res.blob();
  },

  listSessions: () => request<{ sessions: any[] }>("/classroom"),
  createSession: (lessonId: string) =>
    request("/classroom", { method: "POST", body: JSON.stringify({ lesson_id: lessonId }) }),
  getState: (sessionId: string, afterSeq = 0) => request(`/classroom/${sessionId}/state?after_seq=${afterSeq}`),
  advance: (sessionId: string, includeQuiz: boolean) =>
    request(`/classroom/${sessionId}/advance`, {
      method: "POST",
      body: JSON.stringify({ include_quiz: includeQuiz }),
    }),
  summary: (sessionId: string) => request(`/classroom/${sessionId}/summary`, { method: "POST" }),
  closeSession: (sessionId: string) => request(`/classroom/${sessionId}/close`, { method: "POST" }),
  dashboard: (sessionId: string) => request(`/classroom/${sessionId}/dashboard`),
  classReport: (sessionId: string) => request(`/sessions/${sessionId}/class-report`),
  studentDiagnosis: (studentId: string) => request(`/students/${studentId}/diagnosis`),
  quizStats: (quizId: string) => request(`/quiz/${quizId}/stats`),

  spaces: () => request<{ spaces: any[] }>("/rag/spaces"),
  documents: (spaceId: string) => request<{ documents: any[] }>(`/rag/spaces/${spaceId}/documents`),
  upload: async (spaceId: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request(`/rag/spaces/${spaceId}/upload`, { method: "POST", body: form });
  },
  exams: (params: { kp?: string; difficulty?: string; limit?: number } = {}) => {
    const search = new URLSearchParams();
    if (params.kp) search.set("kp", params.kp);
    if (params.difficulty) search.set("difficulty", params.difficulty);
    search.set("limit", String(params.limit || 50));
    return request<{ items: any[]; total: number }>(`/rag/exams?${search.toString()}`);
  },
  ragStats: () => request("/rag/stats"),
  search: (payload: any) => request<{ hits: any[] }>("/rag/search", { method: "POST", body: JSON.stringify(payload) }),

  getSettings: () => request("/settings"),
  updateSettings: (payload: any) => request("/settings", { method: "PUT", body: JSON.stringify(payload) }),
  testSettings: () => request("/settings/test", { method: "POST" }),

  assistantTools: () => request<{ tools: any[]; llm_ready: boolean; mode: string }>("/assistant/tools"),
  assistantChat: (payload: {
    message: string;
    tools_enabled: boolean;
    history: { role: "user" | "assistant"; content: string }[];
    confirm_token?: string;
    conversation_id?: string | null;
  }) => request<any>("/assistant/chat", { method: "POST", body: JSON.stringify(payload) }),
  assistantConversations: () => request<{ conversations: any[] }>("/assistant/conversations"),
  assistantConversation: (id: string) =>
    request<{ conversation: any; messages: any[] }>(`/assistant/conversations/${id}`),
  deleteAssistantConversation: (id: string) =>
    request<{ ok: boolean }>(`/assistant/conversations/${id}`, { method: "DELETE" }),
};
