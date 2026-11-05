<script setup lang="ts">
import { onLoad } from "@dcloudio/uni-app";
import { computed, reactive, ref } from "vue";
import { api, requireLogin } from "../../utils/api";

const quizId = ref("");
const quiz = ref<any>(null);
const answers = reactive<Record<string, string>>({});
const loading = ref(true);
const submitting = ref(false);
const error = ref("");
const already = ref<any>(null);
const retry = ref(false);

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

const items = computed(() => quiz.value?.items || []);
const answeredCount = computed(() => Object.values(answers).filter((v) => String(v || "").trim()).length);
const progress = computed(() => (items.value.length ? Math.round((answeredCount.value / items.value.length) * 100) : 0));

async function load() {
  loading.value = true;
  try {
    quiz.value = await api.quiz(quizId.value);
    error.value = "";
    try {
      already.value = await api.report(quizId.value);
    } catch {
      already.value = null;
    }
  } catch (err: any) {
    error.value = err?.message || "测验加载失败";
  } finally {
    loading.value = false;
  }
}

function pick(item: any, option: string) {
  const letter = (option || "").trim().charAt(0).toUpperCase();
  answers[item.id] = /[A-D]/.test(letter) ? letter : option;
}

function verify(): boolean {
  if (answeredCount.value < items.value.length) {
    const left = items.value.length - answeredCount.value;
    uni.showModal({
      title: "还有题目没答",
      content: `还剩 ${left} 题。确定提交吗？空题按错误计分。`,
      success: (res) => {
        if (res.confirm) doSubmit();
      },
    });
    return false;
  }
  return true;
}

async function submit() {
  if (!verify()) return;
  await doSubmit();
}

async function doSubmit() {
  submitting.value = true;
  error.value = "";
  try {
    const payload = items.value.map((item: any) => ({ item_id: item.id, answer: answers[item.id] || "" }));
    // 后端现在「秒回」：立即落一条 grading 记录并返回，批改在后台任务里跑
    await api.submit(quizId.value, payload);
    uni.showToast({ title: "已交卷，AI 正在批改", icon: "none", duration: 1500 });
    setTimeout(() => uni.redirectTo({ url: `/pages/report/report?quiz_id=${quizId.value}` }), 800);
  } catch (err: any) {
    uni.showModal({
      title: "提交失败",
      content: err?.message || "网络异常，请检查后端服务后重试。",
      showCancel: false,
    });
  } finally {
    submitting.value = false;
  }
}

function difficultyTag(d: string): "success" | "warning" | "error" {
  return d === "hard" ? "error" : d === "medium" ? "warning" : "success";
}

function difficultyLabel(d: string): string {
  return d === "hard" ? "较难" : d === "medium" ? "中等" : "容易";
}

function viewReport() {
  uni.redirectTo({ url: `/pages/report/report?quiz_id=${quizId.value}` });
}
</script>

<template>
  <view class="page">
    <view class="hero">
      <text class="hero-title">随堂测验</text>
      <text class="hero-sub">
        共 {{ items.length || 5 }} 题，每题 10 分。交卷后立即批改，错题会给出步骤级反馈与推荐练习。
      </text>
    </view>

    <view v-if="error" class="error">{{ error }}</view>
    <uni-load-more v-if="loading" status="loading" :content-text="{ contentrefresh: '正在加载题目…' }" />

    <view v-if="already && !retry" class="card">
      <view class="card-title">
        <text>{{ already.status === "grading" ? "你已交卷，AI 正在批改" : "你已提交过本次测验" }}</text>
        <uni-tag
          :text="already.status === 'grading' ? '批改中' : '已交卷'"
          :type="already.status === 'grading' ? 'warning' : 'success'"
          size="small"
          circle
        />
      </view>
      <text v-if="already.status === 'grading'" class="muted" style="display: block">
        报告生成后即可查看分数、步骤反馈与错因分析，稍等几秒后点「查看报告」。
      </text>
      <text v-else class="muted" style="display: block">
        得分 {{ already.score }} / {{ already.max_score }}，正确率 {{ already.percent }}%。
      </text>
      <view class="row" style="margin-top: 24rpx">
        <view class="btn primary" style="flex: 1" @tap="viewReport">查看报告</view>
        <view class="btn" style="flex: 1" @tap="retry = true">再练一遍</view>
      </view>
    </view>

    <template v-if="!loading && quiz && (!already || retry)">
      <view class="card progress-card">
        <view class="row">
          <text class="muted">进度 {{ answeredCount }} / {{ items.length }}</text>
          <view class="bar">
            <view class="bar-fill" :style="{ width: progress + '%' }"></view>
          </view>
          <text class="muted">{{ progress }}%</text>
        </view>
      </view>

      <view v-for="(item, idx) in items" :key="item.id" class="card">
        <view class="row" style="margin-bottom: 12rpx">
          <text class="q-no">第 {{ idx + 1 }} 题</text>
          <uni-tag :text="difficultyLabel(item.difficulty)" :type="difficultyTag(item.difficulty)" size="small" circle />
          <uni-tag :text="item.kp" type="default" size="small" circle />
          <uni-tag
            :text="item.source_type === 'reference_paper' ? '参考试卷' : '教材改编'"
            :type="item.source_type === 'reference_paper' ? 'primary' : 'default'"
            size="small"
            circle
          />
        </view>
        <text class="stem">{{ item.stem }}</text>

        <view v-if="item.qtype === 'choice'" style="margin-top: 16rpx">
          <view
            v-for="opt in item.options"
            :key="opt"
            class="option"
            :class="{ active: answers[item.id] === opt.trim().charAt(0).toUpperCase() }"
            @tap="pick(item, opt)"
          >
            {{ opt }}
          </view>
        </view>
        <view v-else style="margin-top: 16rpx">
          <uni-easyinput v-model="answers[item.id]" placeholder="填写答案，含单位的可只写数值部分" />
          <text class="muted" style="display: block; margin-top: 10rpx">填空/解答题请写最终结果，多解用“或”连接。</text>
        </view>
      </view>

      <view class="btn blue" :class="{ disabled: submitting }" @tap="submit">
        {{ submitting ? "批改中…" : "交卷并查看批改" }}
      </view>
    </template>
  </view>
</template>

<style scoped>
.progress-card {
  padding: 20rpx 26rpx;
}

.q-no {
  font-size: 24rpx;
  font-weight: 700;
  color: #1f5fb4;
  margin-right: 6rpx;
}

.stem {
  display: block;
  font-size: 28rpx;
  line-height: 1.75;
  color: #16233a;
}
</style>
