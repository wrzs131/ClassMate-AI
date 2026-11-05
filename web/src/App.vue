<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { boot, logout, state } from "./store";
import LoginView from "./views/LoginView.vue";
import CoursewareView from "./views/CoursewareView.vue";
import ClassroomView from "./views/ClassroomView.vue";
import AnalyticsView from "./views/AnalyticsView.vue";
import KnowledgeView from "./views/KnowledgeView.vue";

const tab = ref<"courseware" | "classroom" | "analytics" | "knowledge">("courseware");

const tabs = [
  { key: "courseware", label: "备课工作台", hint: "课件生成" },
  { key: "classroom", label: "授课控制台", hint: "课堂码 / 推题" },
  { key: "analytics", label: "学情诊断", hint: "掌握度 / 错因" },
  { key: "knowledge", label: "知识库", hint: "教材 / 真题" },
] as const;

const current = computed(() => {
  switch (tab.value) {
    case "classroom":
      return ClassroomView;
    case "analytics":
      return AnalyticsView;
    case "knowledge":
      return KnowledgeView;
    default:
      return CoursewareView;
  }
});

onMounted(boot);
</script>

<template>
  <div v-if="state.booting" class="splash">
    <div class="splash-inner">
      <div class="logo-big">ClassMate<span>AI</span></div>
      <p>正在准备教师工作台…</p>
    </div>
  </div>

  <LoginView v-else-if="!state.user" />

  <div v-else class="shell">
    <header class="topbar">
      <div class="brand">
        <!-- <div class="brand-row"> -->
        <div class="logo">ClassMate<span>AI</span></div>
        <!-- </div> -->
        <div class="brand-sub">多智能体 · 有理数的加减运算</div>
      </div>
      <nav class="tabs">
        <button
          v-for="item in tabs"
          :key="item.key"
          class="tab"
          :class="{ active: tab === item.key }"
          @click="tab = item.key"
        >
          <span>{{ item.label }}</span>
          <em>{{ item.hint }}</em>
        </button>
      </nav>
      <div class="topbar-right">
        <el-tag :type="state.health?.llm_ready ? 'success' : 'warning'" effect="light" round size="small">
          {{ state.health?.llm_ready ? "模型在线" : "离线演示模式" }}
        </el-tag>
        <span class="user-chip">{{ state.user?.nickname || state.user?.username }}</span>
        <el-button size="small" @click="logout">退出</el-button>
      </div>
    </header>

    <main class="main">
      <component :is="current" />
    </main>

    <footer class="footer">
      <span>ClassMate AI · FastAPI + LangChain + Chroma + Qwen3-VL</span>
      <span>课件题目全部来自知识库真题 / 示例题，可逐题溯源</span>
    </footer>
  </div>
</template>
