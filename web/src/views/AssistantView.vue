<script setup lang="ts">
import { onMounted, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { api } from "../api";
import { state } from "../store";

type Trace = {
  tool: string;
  label: string;
  arguments: Record<string, any>;
  result: string;
  status: string;
  duration_ms: number;
  write?: boolean;
  destructive?: boolean;
};

type Bubble = {
  role: "user" | "assistant";
  content: string;
  traces?: Trace[];
};

type Conversation = {
  id: string;
  title: string;
  message_count: number;
  updated_at: number;
};

const toolsEnabled = ref(true);
const tools = ref<any[]>([]);
const conversations = ref<Conversation[]>([]);
const activeId = ref<string | null>(null);
const messages = ref<Bubble[]>([]);
const input = ref("");
const loading = ref(false);
const switching = ref(false);

const history = ref<{ role: "user" | "assistant"; content: string }[]>([]);

const examples = [
  "列出我所有的课件",
  "最近一堂课的学情怎么样",
  "列出中等难度的有理数加法题",
  "新建一个八年级几何真题库",
  "删除名字为有理数的加减运算的课件（需要二次确认）",
];

const readTools = () => tools.value.filter((item) => !item.write && !item.destructive);
const writeTools = () => tools.value.filter((item) => item.write);
const deleteTools = () => tools.value.filter((item) => item.destructive);

onMounted(async () => {
  loadConversations();
  try {
    const res = await api.assistantTools();
    tools.value = res.tools || [];
  } catch (err: any) {
    ElMessage.warning(err?.message || "工具清单加载失败");
  }
});

async function loadConversations() {
  try {
    const res = await api.assistantConversations();
    conversations.value = res.conversations || [];
  } catch {
    // 历史列表加载失败不阻塞对话
  }
}

function fmt(value: any): string {
  try {
    const text = JSON.stringify(value, null, 2);
    return text.length > 420 ? `${text.slice(0, 420)}…` : text;
  } catch {
    return String(value);
  }
}

function formatTime(ms: number): string {
  if (!ms) return "";
  const date = new Date(ms);
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function useExample(text: string) {
  input.value = text;
}

function newChat() {
  activeId.value = null;
  messages.value = [];
  history.value = [];
  input.value = "";
}

async function openConversation(item: Conversation) {
  if (loading.value || switching.value) return;
  if (activeId.value === item.id && messages.value.length) return;
  switching.value = true;
  try {
    const res = await api.assistantConversation(item.id);
    activeId.value = item.id;
    messages.value = (res.messages || [])
      .filter((msg: any) => msg.content)
      .map((msg: any) => ({
        role: msg.role === "user" ? "user" : "assistant",
        content: msg.content,
        traces: msg.tool_calls || [],
      }));
    history.value = messages.value
      .filter((msg) => msg.content)
      .map((msg) => ({ role: msg.role, content: msg.content }));
  } catch (err: any) {
    ElMessage.error(err?.message || "历史对话加载失败");
  } finally {
    switching.value = false;
  }
}

async function removeConversation(item: Conversation, event: Event) {
  event.stopPropagation();
  if (loading.value) return;
  try {
    await ElMessageBox.confirm(
      `确定删除历史对话「${item.title || "新的对话"}」吗？删除后无法恢复。`,
      "删除对话",
      { confirmButtonText: "删除", cancelButtonText: "取消", type: "warning" }
    );
  } catch {
    return;
  }
  try {
    await api.deleteAssistantConversation(item.id);
    conversations.value = conversations.value.filter((conv) => conv.id !== item.id);
    if (activeId.value === item.id) newChat();
    ElMessage.success("历史对话已删除");
  } catch (err: any) {
    ElMessage.error(err?.message || "删除对话失败");
  }
}

async function send(text?: string) {
  const content = (text ?? input.value).trim();
  if (!content || loading.value) return;
  input.value = "";
  messages.value.push({ role: "user", content });
  history.value.push({ role: "user", content });
  const snapshot = history.value.slice(-8, -1);
  loading.value = true;
  try {
    const res = await api.assistantChat({
      message: content,
      tools_enabled: toolsEnabled.value,
      history: snapshot,
      conversation_id: activeId.value,
    });
    await handleReply(res, content, snapshot);
    if (res.conversation_id) activeId.value = res.conversation_id;
    loadConversations();
  } catch (err: any) {
    messages.value.push({ role: "assistant", content: err?.message || "请求失败，请检查后端服务。" });
    ElMessage.error(err?.message || "AI 助手请求失败");
  } finally {
    loading.value = false;
  }
}

async function handleReply(res: any, content: string, snapshot: any[]) {
  messages.value.push({ role: "assistant", content: res.answer || "（无回复）", traces: res.tool_calls || [] });
  history.value.push({ role: "assistant", content: res.answer || "" });

  if (!res.need_confirm) return;

  const confirm = res.need_confirm;
  try {
    await ElMessageBox.confirm(
      `即将执行「${confirm.label}」，参数：\n${fmt(confirm.arguments)}`,
      "删除操作需要确认",
      { confirmButtonText: "确认执行", cancelButtonText: "取消", type: "warning" }
    );
  } catch {
    const cancel = "已取消，未执行任何删除操作。";
    messages.value.push({ role: "assistant", content: cancel });
    history.value.push({ role: "assistant", content: cancel });
    return;
  }

  const res2 = await api.assistantChat({
    message: content,
    tools_enabled: true,
    history: snapshot,
    confirm_token: confirm.token,
    conversation_id: activeId.value,
  });
  messages.value.push({ role: "assistant", content: res2.answer || "操作已完成。", traces: res2.tool_calls || [] });
  history.value.push({ role: "assistant", content: res2.answer || "" });
  if (res2.conversation_id) activeId.value = res2.conversation_id;
}
</script>

<template>
  <div class="assistant">
    <header class="assistant-head">
      <div>
        <h2>AI 助手</h2>
        <p class="muted">
          用一句话让助手调用 MCP 工具完成查询与增删改；删除类操作必须二次确认。
        </p>
      </div>
      <div class="head-actions">
        <el-tag v-if="!state.health?.llm_ready" type="warning" effect="light" round size="small">
          离线演示模式
        </el-tag>
        <el-switch
          v-model="toolsEnabled"
          inline-prompt
          active-text="MCP 工具模式"
          inactive-text="仅对话"
          size="large"
        />
      </div>
    </header>

    <div class="assistant-body">
      <section class="chat-panel">
        <div class="chat-scroll">
          <div v-if="!messages.length" class="welcome">
            <p class="welcome-title">你好，我是 ClassMate AI 助手</p>
            <p class="muted">
              开启工具模式后，我可以查询课件 / 课堂 / 题库 / 学情，也能新建知识空间、导入真题、开课、改课件、删除数据。
            </p>
            <div class="chips">
              <button v-for="item in examples" :key="item" class="chip" @click="useExample(item)">
                {{ item }}
              </button>
            </div>
          </div>

          <div v-for="(bubble, index) in messages" :key="index" class="bubble-row" :class="bubble.role">
            <div class="bubble">
              <p class="bubble-text">{{ bubble.content }}</p>
              <div v-if="bubble.traces && bubble.traces.length" class="bubble-traces">
                <span class="trace-label">调用了 {{ bubble.traces.length }} 个工具：</span>
                <el-tag
                  v-for="trace in bubble.traces"
                  :key="trace.tool + trace.duration_ms"
                  :type="trace.destructive ? 'danger' : trace.write ? 'warning' : 'info'"
                  size="small"
                  effect="plain"
                >
                  {{ trace.label }} · {{ trace.duration_ms }}ms
                </el-tag>
              </div>
            </div>
          </div>

          <div v-if="loading" class="bubble-row assistant">
            <div class="bubble typing">助手正在思考并调用工具…</div>
          </div>
        </div>

        <div class="composer">
          <el-input
            v-model="input"
            type="textarea"
            :rows="2"
            resize="none"
            placeholder="例如：列出最近一堂课的学情，或：删掉这道题"
            @keydown.enter.exact.prevent="send()"
          />
          <div class="composer-actions">
            <span class="muted">{{ toolsEnabled ? "工具模式：会读写平台数据" : "对话模式：不改动任何数据" }}</span>
            <el-button type="primary" :loading="loading" @click="send()">发送</el-button>
          </div>
        </div>
      </section>

      <aside class="side">
        <div class="side-card history-card">
          <div class="history-head">
            <h3>历史对话 <span class="muted">（{{ conversations.length }}）</span></h3>
            <el-button size="small" plain type="primary" @click="newChat">新对话</el-button>
          </div>
          <div v-if="!conversations.length" class="muted empty">
            还没有历史对话，发送第一条消息后会出现在这里
          </div>
          <div v-else class="conv-list">
            <div
              v-for="conv in conversations"
              :key="conv.id"
              class="conv-item"
              :class="{ active: conv.id === activeId }"
              @click="openConversation(conv)"
            >
              <span class="conv-row">
                <span class="conv-title">{{ conv.title || "新的对话" }}</span>
                <button class="conv-del" title="删除该对话" @click="removeConversation(conv, $event)">删除</button>
              </span>
              <span class="conv-meta">
                <span>{{ formatTime(conv.updated_at) }}</span>
                <span>{{ conv.message_count }} 条</span>
              </span>
            </div>
          </div>
        </div>

        <div class="side-card">
          <h3>可用工具 <span class="muted">（{{ tools.length }}）</span></h3>
          <div class="tool-group">
            <span class="group-label">查询</span>
            <el-tag v-for="item in readTools()" :key="item.name" size="small" effect="plain" :title="item.description">
              {{ item.label }}
            </el-tag>
          </div>
          <div class="tool-group">
            <span class="group-label">写入</span>
            <el-tag v-for="item in writeTools()" :key="item.name" type="warning" size="small" effect="plain" :title="item.description">
              {{ item.label }}
            </el-tag>
          </div>
          <div class="tool-group">
            <span class="group-label">删除</span>
            <el-tag v-for="item in deleteTools()" :key="item.name" type="danger" size="small" effect="plain" :title="item.description">
              {{ item.label }}
            </el-tag>
          </div>
        </div>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.assistant {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.assistant-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 4px 2px;
}

.assistant-head h2 {
  margin: 0 0 6px;
  font-size: 22px;
  color: #16233a;
}

.assistant-head .muted {
  margin: 0;
  color: #6b7a90;
  font-size: 13px;
}

.head-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.assistant-body {
  display: flex;
  gap: 16px;
  min-height: 560px;
}

.chat-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: #fff;
  border: 1px solid #e4ecf7;
  border-radius: 14px;
  overflow: hidden;
}

.chat-scroll {
  flex: 1;
  padding: 18px;
  overflow-y: auto;
  background: #f8fbff;
  max-height: 560px;
}

.welcome {
  background: #fff;
  border: 1px dashed #d7e4f7;
  border-radius: 12px;
  padding: 18px;
}

.welcome-title {
  margin: 0 0 8px;
  font-weight: 700;
  color: #1f5fb4;
}

.welcome .muted {
  margin: 0 0 12px;
  color: #6b7a90;
  font-size: 13px;
  line-height: 1.7;
}

.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.chip {
  border: 1px solid #cfe0f7;
  background: #f2f7ff;
  color: #1f5fb4;
  border-radius: 999px;
  padding: 6px 12px;
  font-size: 12px;
  cursor: pointer;
}

.chip:hover {
  background: #e5efff;
}

.bubble-row {
  display: flex;
  margin-bottom: 14px;
}

.bubble-row.user {
  justify-content: flex-end;
}

.bubble-row.assistant {
  justify-content: flex-start;
}

.bubble {
  max-width: 78%;
  padding: 12px 14px;
  border-radius: 12px;
  font-size: 14px;
  line-height: 1.7;
  background: #fff;
  border: 1px solid #e4ecf7;
  color: #16233a;
}

.bubble-row.user .bubble {
  background: #1f5fb4;
  border-color: #1f5fb4;
  color: #fff;
}

.bubble-text {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
}

.bubble-traces {
  margin-top: 10px;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}

.trace-label {
  font-size: 12px;
  color: #6b7a90;
}

.typing {
  color: #1f5fb4;
  font-size: 13px;
}

.composer {
  border-top: 1px solid #e4ecf7;
  padding: 12px 14px 14px;
  background: #fff;
}

.composer-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 10px;
}

.composer-actions .muted {
  font-size: 12px;
  color: #6b7a90;
}

.side {
  width: 330px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.side-card {
  background: #fff;
  border: 1px solid #e4ecf7;
  border-radius: 14px;
  padding: 14px 16px;
  max-height: 330px;
  overflow-y: auto;
}

.history-card {
  display: flex;
  flex-direction: column;
  max-height: 480px;
  overflow: hidden;
}

.history-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 10px;
}

.history-head h3 {
  margin: 0;
  font-size: 15px;
  color: #16233a;
}

.side-card h3 {
  margin: 0 0 10px;
  font-size: 15px;
  color: #16233a;
}

.side-card h3 .muted,
.history-head h3 .muted {
  font-weight: 400;
  font-size: 12px;
  color: #8a97a8;
}

.empty {
  font-size: 13px;
  color: #8a97a8;
}

.conv-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  overflow-y: auto;
  min-height: 0;
  /* 最多展示 5 条，超出后出现滚动条 */
  max-height: 322px;
  padding-right: 2px;
}

.conv-item {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 6px;
  text-align: left;
  border: 1px solid #eef3fb;
  background: #fbfdff;
  border-radius: 10px;
  padding: 10px 12px;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
}

.conv-item:hover {
  border-color: #cfe0f7;
  background: #f5f9ff;
}

.conv-item.active {
  border-color: #1f5fb4;
  background: #eef5ff;
}

.conv-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.conv-del {
  flex-shrink: 0;
  border: none;
  background: transparent;
  color: #c45656;
  font-size: 11px;
  line-height: 1;
  padding: 4px 6px;
  border-radius: 6px;
  cursor: pointer;
}

.conv-del:hover {
  background: #fdecec;
  color: #a73232;
}

.conv-title {
  flex: 1;
  min-width: 0;
  font-size: 13px;
  color: #16233a;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.conv-item.active .conv-title {
  color: #1f5fb4;
}

.conv-meta {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  color: #8a97a8;
}

.tool-group {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-bottom: 10px;
}

.group-label {
  font-size: 12px;
  color: #6b7a90;
  margin-right: 2px;
}
</style>
