<script setup lang="ts">
import { onShow } from "@dcloudio/uni-app";
import { ref } from "vue";
import { api, clearAuth, getJoined, getUser, requireLogin, setJoined } from "../../utils/api";

const user = ref<any>(null);
const joined = ref<any>(null);
const joinedStatus = ref("active");
const classCode = ref("");
const error = ref("");
const loading = ref(false);

onShow(() => {
  if (!requireLogin()) return;
  user.value = getUser();
  // 「加入的课堂」按账号分开存：切回自己的账号，之前加入的课堂依然在
  joined.value = getJoined();
  joinedStatus.value = "active";
  validateJoined();
});

/** 课堂可能已被老师结束/关闭，或自己已退班：回首页时校验一次，避免显示一个进不去的课堂 */
async function validateJoined() {
  const item = joined.value;
  if (!item?.id) return;
  try {
    const data: any = await api.state(item.id);
    joinedStatus.value = data?.session?.status || "active";
  } catch (err: any) {
    if (String(err?.message || "").includes("加入课堂")) {
      setJoined(null);
      joined.value = null;
    }
  }
}

async function join() {
  error.value = "";
  const code = classCode.value.trim();
  if (!/^\d{6}$/.test(code)) {
    error.value = "课堂码是 6 位数字，请检查后重试";
    return;
  }
  loading.value = true;
  try {
    const data: any = await api.join(code);
    const item = {
      id: data.session.id,
      class_code: data.session.class_code,
      lesson_title: data.lesson?.title,
    };
    setJoined(item);
    joined.value = item;
    uni.navigateTo({ url: "/pages/classroom/classroom" });
  } catch (err: any) {
    error.value = err?.message || "加入课堂失败";
  } finally {
    loading.value = false;
  }
}

function enterClass() {
  uni.navigateTo({ url: "/pages/classroom/classroom" });
}

function openMe() {
  uni.navigateTo({ url: "/pages/me/me" });
}

function leaveClass() {
  const current = joined.value;
  uni.showModal({
    title: "退出课堂？",
    content: "退出后老师端会看到你已离开课堂，重新进入需要输入课堂码。",
    success: async (res) => {
      if (!res.confirm) return;
      // 必须同步到后端，否则教师端成员列表与课堂事件流不会变化
      if (current?.id) {
        try {
          await api.leave(current.id);
        } catch (err: any) {
          uni.showToast({ title: err?.message || "退出同步失败", icon: "none" });
        }
      }
      setJoined(null);
      joined.value = null;
    },
  });
}

function logout() {
  clearAuth();
  // 不再清「加入的课堂」：记录按账号分别存储，切回自己的账号时课堂卡片应当还在
  joined.value = null;
  uni.reLaunch({ url: "/pages/login/login" });
}
</script>

<template>
  <view class="page">
    <view class="hero">
      <view class="row">
        <uni-icons type="person-filled" size="26" color="#ffe66b" />
        <text class="hero-title">你好，{{ user?.nickname || "同学" }}</text>
      </view>
      <text class="hero-sub">
        今天的课是《有理数的加减运算》。跟着老师一步步看符号、算绝对值，遇到不会的先点“提问”，助教会先给你提示。
      </text>
    </view>

    <view v-if="joined" class="card">
      <view class="card-title">
        <text>我的课堂</text>
        <uni-tag v-if="joinedStatus === 'closed'" text="课堂已关闭" type="info" size="small" circle />
        <uni-tag v-else-if="joinedStatus === 'finished'" text="课堂已结束" type="warning" size="small" circle />
        <uni-tag v-else text="已加入" type="success" size="small" circle />
      </view>
      <text style="font-size: 30rpx; font-weight: 700; display: block">{{ joined.lesson_title || "互动课堂" }}</text>
      <text class="muted" style="display: block; margin-top: 8rpx">课堂码 {{ joined.class_code }}</text>

      <view class="row" style="margin-top: 24rpx">
        <view class="btn blue" style="flex: 1" @tap="enterClass">进入课堂</view>
        <view class="btn" style="flex: 1" @tap="openMe">我的学情</view>
      </view>
      <view class="btn ghost" style="margin-top: 12rpx" @tap="leaveClass">退出课堂</view>
    </view>

    <view v-else class="card">
      <view class="card-title">
        <text>加入课堂</text>
        <text class="muted">输入老师给的 6 位课堂码</text>
      </view>
      <uni-easyinput v-model="classCode" type="number" placeholder="例如 507921" :maxlength="6" />
      <view v-if="error" class="error">{{ error }}</view>
      <view class="btn primary" style="margin-top: 24rpx" :class="{ disabled: loading }" @tap="join">
        {{ loading ? "加入中…" : "加入课堂" }}
      </view>
      <uni-load-more v-if="loading" status="loading" :content-text="{ contentrefresh: '正在校验课堂码…' }" />
      <text class="muted" style="display: block; margin-top: 18rpx; line-height: 1.7">
        课堂码在教师端「授课控制台」开课后显示，只对进行中的课堂有效。
      </text>
    </view>

    <view class="card">
      <view class="card-title">
        <text>我的学习</text>
        <text class="muted">掌握度 · 错因 · 推荐题</text>
      </view>
      <view class="row">
        <view class="btn" style="flex: 1" @tap="openMe">查看学情报告</view>
        <view class="btn ghost" style="flex: 1" @tap="logout">退出登录</view>
      </view>
    </view>
  </view>
</template>
