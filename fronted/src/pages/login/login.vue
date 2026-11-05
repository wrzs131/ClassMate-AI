<script setup lang="ts">
import { onReady } from "@dcloudio/uni-app";
import { computed, ref } from "vue";
import { api, apiBase, DEFAULT_BASE, getToken, setApiBase, setToken, setUser } from "../../utils/api";

const mode = ref<"login" | "register">("login");
const modeIndex = computed(() => (mode.value === "login" ? 0 : 1));
const username = ref("student");
const password = ref("demo123456");
const nickname = ref("小明");
const base = ref(apiBase());
const showBase = ref(false);
const error = ref("");
const loading = ref(false);
// 已登录时不在挂载任何 uni-ui 子组件，避免「挂载中就被 reLaunch 销毁」导致小程序端
// 自定义组件 __l 事件回调拿到已销毁实例（表现为 Cannot read property 'forceUpdate' of undefined）
const loggedIn = ref(!!getToken());

// 首屏渲染完成（onReady）后再跳首页：在 onLoad/onShow 阶段 reLaunch 会把正在挂载、
// 正在参与布局的页面整棵销毁，微信基础库随后会抛
// Cannot read property 'forceUpdate' of undefined（内部 children 引用已失效的节点）
onReady(() => {
  if (loggedIn.value) {
    uni.reLaunch({ url: "/pages/home/home" });
  }
});

function onModeChange(e: any) {
  mode.value = Number(e?.currentIndex) === 1 ? "register" : "login";
  error.value = "";
}

function fillDemo() {
  username.value = "student";
  password.value = "demo123456";
  nickname.value = "小明";
}

async function submit() {
  error.value = "";
  if (!username.value.trim()) {
    error.value = "请输入账号";
    return;
  }
  loading.value = true;
  try {
    if (showBase.value) setApiBase(base.value.trim() || DEFAULT_BASE);
    const data =
      mode.value === "login"
        ? await api.login(username.value.trim(), password.value)
        : await api.register({
            role: "student",
            username: username.value.trim(),
            password: password.value,
            nickname: nickname.value.trim() || username.value.trim(),
          });
    setToken(data.token);
    setUser(data.user);
    uni.reLaunch({ url: "/pages/home/home" });
  } catch (err: any) {
    error.value = err?.message || "操作失败";
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <view class="page">
    <view v-if="loggedIn" class="card" style="margin-top: 60rpx">
      <text class="muted" style="line-height: 1.8">已登录，正在返回首页…</text>
    </view>

    <template v-else>
    <view class="hero">
      <view class="row">
        <uni-icons type="staff-filled" size="24" color="#ffe66b" />
        <text class="hero-title">课堂里的 AI 助教，<text class="hl">先提示再给答案</text></text>
      </view>
      <text class="hero-sub">
        登录后输入老师给的 6 位课堂码即可进入课堂：看讲解、随时提问（可拍照上传手写步骤）、做随堂测验、查看错因报告。
      </text>
    </view>

    <view class="card">
      <uni-segmented-control
        :current="modeIndex"
        :values="['登录', '注册']"
        active-color="#16233a"
        @clickItem="onModeChange"
      />

      <text class="label" style="margin-top: 26rpx">账号</text>
      <uni-easyinput v-model="username" placeholder="student" />

      <text class="label" style="margin-top: 20rpx">密码</text>
      <uni-easyinput v-model="password" type="password" placeholder="demo123456" />

      <text v-if="mode === 'register'" class="label" style="margin-top: 20rpx">昵称</text>
      <uni-easyinput v-if="mode === 'register'" v-model="nickname" placeholder="小明" />

      <view v-if="error" class="error">{{ error }}</view>

      <view class="btn primary" style="margin-top: 26rpx" :class="{ disabled: loading }" @tap="submit">
        {{ loading ? "处理中…" : mode === "login" ? "进入课堂" : "注册并进入" }}
      </view>

      <view class="row" style="justify-content: space-between; margin-top: 18rpx">
        <view class="btn ghost" @tap="fillDemo">填入演示账号</view>
        <!-- <view class="btn ghost" @tap="showBase = !showBase">接口地址</view> -->
      </view>

      <!-- <view v-if="showBase" style="margin-top: 16rpx">
        <text class="label">后端地址（默认 {{ DEFAULT_BASE }}）</text>
        <uni-easyinput v-model="base" placeholder="http://127.0.0.1:8001/api" />
      </view> -->

      <text class="muted" style="display: block; margin-top: 20rpx; line-height: 1.7">
        <!-- 演示账号：student / demo123456；也可以自己注册。教师端在 web/ 目录。 -->
      </text>
    </view>
    </template>
  </view>
</template>
