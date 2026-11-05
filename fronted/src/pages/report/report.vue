<script setup lang="ts">
import { onLoad } from "@dcloudio/uni-app";
import { computed, ref } from "vue";
import { api, getJoined, requireLogin } from "../../utils/api";

const quizId = ref("");
const report = ref<any>(null);
const loading = ref(true);
const pending = ref(false);
const error = ref("");

onLoad((query: any) => {
  if (!requireLogin()) return;
  quizId.value = (query?.quiz_id as string) || "";
  if (!quizId.value) {
    error.value = "缺少测验编号";
    loading.value = false;
    return;
  }
  load();
});

const items = computed(() => report.value?.items || []);
const mastery = computed(() => report.value?.mastery || []);
const percent = computed(() => Number(report.value?.percent || 0));

async function load(attempt = 0) {
  loading.value = true;
  try {
    const data: any = await api.report(quizId.value);
    // 交卷接口现在"秒回"，服务端在后台批改：报告里 status=grading 时继续轮询
    if (data?.status === "grading") {
      report.value = null;
      pending.value = true;
      error.value = "";
      loading.value = false;
      if (attempt < 90) setTimeout(() => load(attempt + 1), 2000);
      else {
        pending.value = false;
        error.value = "批改耗时较长，请稍后在「我的」里重新打开报告。";
      }
      return;
    }
    if (data?.status === "failed") {
      report.value = null;
      pending.value = false;
      loading.value = false;
      error.value = data?.error || "批改失败，请重新交卷。";
      return;
    }
    report.value = data;
    error.value = "";
    pending.value = false;
    loading.value = false;
  } catch (err: any) {
    const message = err?.message || "报告加载失败";
    // 刚交卷、占位记录还没落库时也会 404：同样等待重试
    if ((message.includes("还没有提交记录") || message.includes("404")) && attempt < 30) {
      pending.value = true;
      loading.value = false;
      setTimeout(() => load(attempt + 1), 2000);
      return;
    }
    pending.value = false;
    error.value = message;
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
  if (getJoined()?.id) uni.redirectTo({ url: "/pages/classroom/classroom" });
  else uni.reLaunch({ url: "/pages/home/home" });
}

function openMe() {
  uni.navigateTo({ url: "/pages/me/me" });
}
</script>

<template>
  <view class="page">
    <view class="hero">
      <text class="hero-title">本次测验报告</text>
      <text class="hero-sub">批改不只判对错：每题都给出错因与下一步建议。</text>
      <view v-if="report" class="row" style="margin-top: 22rpx">
        <text class="code-big" style="font-size: 36rpx; letter-spacing: 2rpx">
          {{ report.score }} / {{ report.max_score }}
        </text>
        <uni-tag :text="`正确率 ${percent}%`" type="success" size="normal" circle />
      </view>
    </view>

    <view v-if="error && !pending" class="error">{{ error }}</view>
    <uni-load-more v-if="loading" status="loading" :content-text="{ contentrefresh: '正在加载报告…' }" />
    <uni-load-more
      v-else-if="pending"
      status="loading"
      :content-text="{ contentrefresh: 'AI 正在批改，报告马上就好…' }"
    />

    <template v-if="report">
      <view class="card">
        <view class="card-title">
          <text>诊断结论</text>
          <uni-tag text="多智能体诊断" type="warning" size="small" circle />
        </view>
        <text class="summary">{{ report.diagnosis?.summary || "暂无诊断结论" }}</text>
        <view v-if="report.weak_points?.length" class="row" style="margin-top: 16rpx">
          <text class="muted">薄弱知识点</text>
          <uni-tag v-for="kp in report.weak_points" :key="kp" :text="kp" type="error" size="small" circle />
        </view>
      </view>

      <view class="card">
        <view class="card-title">
          <text>知识点掌握度</text>
          <text class="muted">答对难题加分更多</text>
        </view>
        <view v-if="!mastery.length" class="empty">还没有掌握度数据</view>
        <view v-for="row in mastery" :key="row.kp" class="kp-row">
          <view class="row">
            <text class="kp-name">{{ row.kp }}</text>
            <uni-tag :text="masteryLabel(row.score)" :type="barType(row.score)" size="small" circle />
            <text class="muted">{{ Math.round(Number(row.score) * 100) }}%</text>
          </view>
          <view class="bar" style="margin: 10rpx 0 0">
            <view class="bar-fill" :class="barClass(row.score)" :style="{ width: Math.round(Number(row.score) * 100) + '%' }"></view>
          </view>
        </view>
      </view>

      <view class="card">
        <view class="card-title">
          <text>逐题反馈</text>
          <text class="muted">点击题目标题展开解析</text>
        </view>
        <view v-for="(item, idx) in items" :key="item.quiz_item_id" class="item">
          <view class="row">
            <text class="q-no">第 {{ idx + 1 }} 题</text>
            <uni-tag :text="item.correct ? '正确' : '错误'" :type="item.correct ? 'success' : 'error'" size="small" circle />
            <text class="muted">{{ item.points }} / {{ item.points_max }} 分</text>
          </view>
          <text class="stem">{{ item.stem }}</text>
          <text class="muted" style="display: block; margin-top: 10rpx">
            你的答案：{{ item.student_answer || "（未作答）" }}
            <template v-if="!item.correct"> · 正确答案：{{ item.answer }}</template>
          </text>
          <uni-tag
            v-if="!item.correct && item.error_type"
            :text="`错因：${item.error_type}`"
            type="warning"
            size="small"
            circle
            style="margin-top: 10rpx"
          />

          <uni-collapse style="margin-top: 12rpx">
            <uni-collapse-item title="步骤反馈与解析" border="show">
              <view class="detail">
                <text v-for="(fb, i) in item.step_feedback || []" :key="i" class="script-text">· {{ fb }}</text>
                <text v-if="item.analysis" class="script-text" style="margin-top: 10rpx">解析：{{ item.analysis }}</text>
                <text class="muted" style="display: block; margin-top: 10rpx">来源：{{ item.source }}</text>
              </view>
            </uni-collapse-item>
          </uni-collapse>
        </view>
      </view>

      <view v-if="report.error_counts && Object.keys(report.error_counts).length" class="card">
        <view class="card-title">
          <text>错因分布</text>
        <text class="muted">累计统计</text>
        </view>
        <view class="row">
          <uni-tag
            v-for="(count, key) in report.error_counts"
            :key="key"
            :text="`${key} × ${count}`"
            type="error"
            size="small"
            circle
          />
        </view>
      </view>

      <view v-if="report.recommended?.length" class="card">
        <view class="card-title">
          <text>下一步练什么</text>
          <uni-tag :text="`${report.recommended.length} 题`" type="success" size="small" circle />
        </view>
        <text class="muted" style="display: block; margin-bottom: 12rpx">同知识点优先，其次考虑错题同类题：</text>
        <view v-for="(rec, i) in report.recommended" :key="rec.id" class="rec">
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
        <view class="btn" style="flex: 1" @tap="openMe">我的学情</view>
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

.q-no {
  font-size: 24rpx;
  font-weight: 700;
  color: #1f5fb4;
}

.item {
  padding: 18rpx 0;
  border-bottom: 2rpx solid rgba(22, 35, 58, 0.06);
}

.item:last-child {
  border-bottom: none;
}

.stem {
  display: block;
  font-size: 27rpx;
  line-height: 1.7;
  color: #16233a;
  margin-top: 10rpx;
}

.detail {
  background: #fbf8f1;
  border-radius: 16rpx;
  padding: 18rpx 20rpx;
  margin-top: 14rpx;
}

.rec {
  padding: 14rpx 0;
  border-bottom: 2rpx solid rgba(22, 35, 58, 0.06);
}

.rec:last-child {
  border-bottom: none;
}
</style>
