<script setup lang="ts">
import { ref } from "vue";
import { getApiBase, setApiBase } from "../api";
import { login, register } from "../store";

const mode = ref<"login" | "register">("login");
const username = ref("teacher");
const password = ref("demo123456");
const nickname = ref("王老师");
const apiBase = ref(getApiBase());
const showAdvanced = ref(false);
const error = ref("");
const loading = ref(false);

const modeOptions = [
  { label: "登录", value: "login" },
  { label: "注册", value: "register" },
];

async function submit() {
  error.value = "";
  if (!username.value.trim()) {
    error.value = "请输入账号";
    return;
  }
  loading.value = true;
  try {
    if (mode.value === "login") {
      await login(username.value.trim(), password.value);
    } else {
      await register({
        role: "teacher",
        username: username.value.trim(),
        password: password.value,
        nickname: nickname.value.trim() || username.value.trim(),
      });
    }
  } catch (err: any) {
    error.value = err?.message || "操作失败";
  } finally {
    loading.value = false;
  }
}

function saveBase() {
  setApiBase(apiBase.value.trim() || "/api");
  showAdvanced.value = false;
}

function useDemo() {
  username.value = "teacher";
  password.value = "demo123456";
}
</script>

<template>
  <div class="login">
    <section class="login-hero">
      <h1>不只生成课件，<br />更把<em>真题、讲解、批改</em>串成一堂课。</h1>
      <p>
        面向中小学课堂的多智能体 AI 助教：课件里的每道题都能追溯到题库，
        讲解按“生活类比 → 分步推导 → 易错点反例 → 真题应用”展开，学生提问先给提示、不直接给答案。
      </p>
      <div class="hero-points">
        <div class="hero-point">
          <b>01 题目不简单</b>
          <span>真题优先组卷 + 难度分层（易/中/难），不再是“随便编两道”的通用 AI 课件。</span>
        </div>
        <div class="hero-point">
          <b>02 讲解够通俗</b>
          <span>四段式讲稿 + 生活账本类比，把“异号相加取绝对值大的符号”讲成看得见的动作。</span>
        </div>
        <div class="hero-point">
          <b>03 学生真会做</b>
          <span>苏格拉底式分级提示、逐题错因归类、掌握度画像与同知识点真题推荐。</span>
        </div>
      </div>
    </section>

    <section class="login-panel">
      <div class="login-box">
        <h2>{{ mode === "login" ? "教师登录" : "注册教师账号" }}</h2>
        <p class="muted">当前演示章节：北师大版七年级上册 · 有理数的加减运算</p>

        <el-segmented v-model="mode" :options="modeOptions" block size="large" style="margin-bottom: 18px" />

        <el-form label-position="top" @submit.prevent>
          <el-form-item label="账号">
            <el-input v-model="username" placeholder="teacher" autocomplete="username" clearable />
          </el-form-item>
          <el-form-item v-if="mode === 'register'" label="昵称">
            <el-input v-model="nickname" placeholder="王老师" />
          </el-form-item>
          <el-form-item label="密码">
            <el-input
              v-model="password"
              type="password"
              placeholder="demo123456"
              autocomplete="current-password"
              show-password
              @keyup.enter="submit"
            />
          </el-form-item>
        </el-form>

        <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon style="margin-bottom: 10px" />

        <el-button
          type="primary"
          size="large"
          style="width: 100%"
          :loading="loading"
          @click="submit"
        >
          {{ mode === "login" ? "进入工作台" : "注册并进入" }}
        </el-button>

        <p class="login-hint">
          <!-- 演示账号：<b>teacher / demo123456</b>（教师）、<b>student / demo123456</b>（学生·小程序端）<br /> -->
          <!-- 学生端在 <b>fronted/</b>（小程序端），登录后输入教师开课的 6 位课堂码即可入班。 -->
        </p>

        <div class="row" style="justify-content: space-between; margin-top: 10px">
          <el-button link type="primary" @click="useDemo">填入演示账号</el-button>
          <!-- <el-button link type="info" @click="showAdvanced = !showAdvanced">接口地址</el-button> -->
        </div>

        <div v-if="showAdvanced" style="margin-top: 10px">
          <p class="muted" style="margin: 0 0 6px">API Base（默认 /api，开发时由 Vite 代理到 8001）</p>
          <div class="row">
            <el-input v-model="apiBase" style="flex: 1" placeholder="/api" />
            <el-button @click="saveBase">保存</el-button>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>
