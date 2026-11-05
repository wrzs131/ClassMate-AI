<script setup lang="ts">
import { onShow } from "@dcloudio/uni-app";
import { computed, ref } from "vue";
import { api, getJoined, getUser, requireLogin } from "../../utils/api";

const data = ref<any>(null);
const loading = ref(true);
const error = ref("");
const user = ref<any>(null);

onShow(() => {
  if (!requireLogin()) return;
  user.value = getUser();
  load();
});

const mastery = computed(() => data.value?.mastery || []);
const attempts = computed(() => data.value?.attempts || []);
const recommended = computed(() => (data.value?.recommended || []).slice(0, 5));

async function load() {
  loading.value = true;
  try {
    data.value = await api.myDiagnosis();
    error.value = "";
  } catch (err: any) {
    error.value = err?.message || "学情加载失败";
  } finally {
    loading.value = false;
  }
}

function barClass(score: number): string {
  const value = Number(score || 0);
  if (value < 0.6) return "bad";
  if (value < 0.8) return "warn";
  return "";
}

function barType(score: number): "error" | "warning" | "success" {
  const value = Number(score || 0);
  if (value < 0.6) return "error";
  if (value < 0.8) return "warning";
  return "success";
}

function masteryLabel(score: number): string {
  const value = Number(score || 0);
  if (value < 0.6) return "需加强";
  if (value < 0.8) return "基本掌握";
  return "掌握良好";
}

function backClass() {
  if (getJoined()?.id) uni.navigateTo({ url: "/pages/classroom/classroom" });
  else uni.reLaunch({ url: "/pages/home/home" });
}

function backHome() {
  uni.reLaunch({ url: "/pages/home/home" });
}
</script>

<template>
  <view class="page">
    <view class="hero">
      <text class="hero-title">{{ data?.student?.nickname || user?.nickname || "同学" }} 的学情画像</text>
      <text class="hero-sub">掌握度按难度加权更新；薄弱点会自动推荐同知识点练习。</text>
    </view>

    <view v-if="error" class="error">{{ error }}</view>
    <uni-load-more v-if="loading" status="loading" :content-text="{ contentrefresh: '正在生成诊断…' }" />

    <template v-if="data">
      <view class="card">
        <view class="card-title">
          <text>诊断建议</text>
          <uni-tag text="学习路径" type="warning" size="small" circle />
        </view>
        <text class="summary">{{ data.summary }}</text>
        <view v-if="data.weak_points?.length" class="row" style="margin-top: 16rpx">
          <text class="muted">薄弱知识点</text>
          <uni-tag v-for="kp in data.weak_points" :key="kp" :text="kp" type="error" size="small" circle />
        </view>
      </view>

      <view class="card">
        <view class="card-title">
          <text>知识点掌握度</text>
          <text class="muted">共 {{ mastery.length }} 个知识点</text>
        </view>
        <view v-if="!mastery.length" class="empty">还没有作答记录，先完成一次随堂测验。</view>
        <view v-for="row in mastery" :key="row.kp" class="kp-row">
          <view class="row">
            <text class="kp-name">{{ row.kp }}</text>
            <uni-tag :text="masteryLabel(row.score)" :type="barType(row.score)" size="small" circle />
            <text class="muted">{{ Math.round(Number(row.score) * 100) }}% · {{ row.attempts }} 次</text>
          </view>
          <view class="bar" style="margin: 10rpx 0 0">
            <view class="bar-fill" :class="barClass(row.score)" :style="{ width: Math.round(Number(row.score) * 100) + '%' }"></view>
          </view>
        </view>
      </view>

      <view v-if="data.error_counts && Object.keys(data.error_counts).length" class="card">
        <view class="card-title">
          <text>错因分布</text>
          <text class="muted">老师端同步可见</text>
        </view>
        <view class="row">
          <uni-tag
            v-for="(count, key) in data.error_counts"
            :key="key"
            :text="`${key} × ${count}`"
            type="error"
            size="small"
            circle
          />
        </view>
      </view>

      <view class="card">
        <view class="card-title">
          <text>最近作答</text>
          <text class="muted">最近 20 条</text>
        </view>
        <view v-if="!attempts.length" class="empty">暂无作答记录</view>
        <view v-for="row in attempts" :key="row.id" class="attempt">
          <view class="row">
            <uni-tag :text="row.correct ? '正确' : '错误'" :type="row.correct ? 'success' : 'error'" size="small" circle />
            <uni-tag :text="row.kp" type="default" size="small" circle />
            <text v-if="row.error_type" class="muted">{{ row.error_type }}</text>
          </view>
          <text class="stem">{{ row.stem }}</text>
          <text class="muted" style="display: block; margin-top: 8rpx">我的答案：{{ row.answer || "（未作答）" }}</text>
        </view>
      </view>

      <view v-if="recommended.length" class="card">
        <view class="card-title">
          <text>为你推荐的练习</text>
          <uni-tag :text="`${recommended.length} 题`" type="success" size="small" circle />
        </view>
        <view v-for="(rec, i) in recommended" :key="rec.id" class="rec">
          <text class="script-text">{{ i + 1 }}. {{ rec.stem }}</text>
          <view class="row" style="margin-top: 8rpx">
            <uni-tag :text="rec.difficulty" type="default" size="small" circle />
            <uni-tag
              :text="rec.source_type === 'reference_paper' ? '参考试卷' : '教材改编'"
              :type="rec.source_type === 'reference_paper' ? 'primary' : 'default'"
              size="small"
              circle
            />
          </view>
        </view>
      </view>

      <view class="row">
        <view class="btn primary" style="flex: 1" @tap="backClass">回到课堂</view>
        <view class="btn" style="flex: 1" @tap="backHome">首页</view>
      </view>
    </template>
  </view>
</template>

<style scoped>
.summary {
  display: block;
  font-size: 27rpx;
  line-height: 1.8;
  color: #16233a;
  background: #fbf8f1;
  border-radius: 18rpx;
  padding: 20rpx 22rpx;
}

.kp-row {
  padding: 14rpx 0;
  border-bottom: 2rpx solid rgba(22, 35, 58, 0.06);
}

.kp-row:last-child {
  border-bottom: none;
}

.kp-name {
  font-size: 25rpx;
  color: #16233a;
}

.attempt {
  padding: 16rpx 0;
  border-bottom: 2rpx solid rgba(22, 35, 58, 0.06);
}

.attempt:last-child {
  border-bottom: none;
}

.stem {
  display: block;
  font-size: 26rpx;
  line-height: 1.7;
  color: #16233a;
  margin-top: 8rpx;
}

.rec {
  padding: 14rpx 0;
  border-bottom: 2rpx solid rgba(22, 35, 58, 0.06);
}

.rec:last-child {
  border-bottom: none;
}
</style>
