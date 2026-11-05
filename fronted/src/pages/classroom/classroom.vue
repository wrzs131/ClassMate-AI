<script setup lang="ts">
import { onHide, onShow, onUnload } from "@dcloudio/uni-app";
import { computed, ref } from "vue";
import { api, getJoined, readImageBase64, requireLogin, setJoined } from "../../utils/api";

const state = ref<any>(null);
const joined = ref<any>(null);
const error = ref("");
const loading = ref(false);
const asking = ref(false);
const question = ref("");
const pickedImage = ref("");
const askResult = ref<any>(null);
let timer: any = null;

const slide = computed(() => state.value?.current_slide || null);
const script = computed(() => slide.value?.script || {});
const latestQuiz = computed(() => state.value?.latest_quiz || null);
const finished = computed(() => state.value?.session?.status === "finished");
const events = computed(() => (state.value?.events || []).slice(-8).reverse());

onShow(() => {
  if (!requireLogin()) return;
  joined.value = getJoined();
  if (!joined.value?.id) {
    uni.showModal({
      title: "还没加入课堂",
      content: "请先在首页输入老师给的 6 位课堂码。",
      showCancel: false,
      success: () => uni.navigateBack(),
    });
    return;
  }
  load();
  startPolling();
});

onHide(stopPolling);
onUnload(stopPolling);

async function load() {
  if (!joined.value?.id) return;
  loading.value = true;
  try {
    state.value = await api.state(joined.value.id);
    error.value = "";
    if (state.value?.session?.class_code) {
      setJoined({
        id: state.value.session.id,
        class_code: state.value.session.class_code,
        lesson_title: state.value.lesson?.title,
      });
    }
  } catch (err: any) {
    error.value = err?.message || "课堂信息加载失败";
    // 学生已退出课堂（或在别处退班）后后端会拒绝访问，这里直接清理本地状态并返回首页
    if (String(error.value).includes("加入课堂")) {
      stopPolling();
      setJoined(null);
      joined.value = null;
      uni.showToast({ title: "你已不在该课堂中", icon: "none" });
      setTimeout(() => uni.reLaunch({ url: "/pages/home/home" }), 800);
    }
  } finally {
    loading.value = false;
  }
}

function startPolling() {
  stopPolling();
  timer = setInterval(load, 5000);
}

function stopPolling() {
  if (timer) {
    clearInterval(timer);
    timer = null;
  }
}

async function chooseImage() {
  try {
    const res: any = await new Promise((resolve, reject) => {
      uni.chooseImage({ count: 1, sizeType: ["compressed"], success: resolve, fail: reject });
    });
    const path = (res.tempFilePaths || [])[0];
    if (!path) return;
    pickedImage.value = path;
    uni.showToast({ title: "已选择图片，可补充说明后提问", icon: "none" });
  } catch {
    uni.showToast({ title: "未选择图片", icon: "none" });
  }
}

async function ask() {
  if (!joined.value?.id) return;
  if (!question.value.trim() && !pickedImage.value) {
    uni.showToast({ title: "先写下你卡住的地方", icon: "none" });
    return;
  }
  asking.value = true;
  try {
    let base64 = "";
    if (pickedImage.value) {
      try {
        base64 = await readImageBase64(pickedImage.value);
      } catch {
        uni.showToast({ title: "图片读取失败，改为文字提问", icon: "none" });
      }
    }
    const data: any = await api.ask(joined.value.id, question.value.trim(), base64 || undefined);
    askResult.value = data;
    question.value = "";
    pickedImage.value = "";
    load();
  } catch (err: any) {
    uni.showModal({ title: "提问失败", content: err?.message || "请稍后重试", showCancel: false });
  } finally {
    asking.value = false;
  }
}

function goQuiz() {
  if (!latestQuiz.value) return;
  uni.navigateTo({ url: `/pages/quiz/quiz?quiz_id=${latestQuiz.value.id}` });
}

function openReport() {
  if (!latestQuiz.value) return;
  uni.navigateTo({ url: `/pages/report/report?quiz_id=${latestQuiz.value.id}` });
}

function goMe() {
  uni.navigateTo({ url: "/pages/me/me" });
}

function eventTagType(e: any): "success" | "warning" | "primary" | "default" {
  if (e?.role === "student") return "success";
  if (e?.role === "teacher") return "warning";
  return "default";
}

function difficultyTagType(d: string): "success" | "warning" | "error" {
  return d === "hard" ? "error" : d === "medium" ? "warning" : "success";
}

function difficultyLabel(d: string): string {
  return d === "hard" ? "较难" : d === "medium" ? "中等" : "容易";
}

function eventLabel(e: any): string {
  const map: Record<string, string> = {
    slide_start: "翻到新一页",
    teacher_speak: "老师讲解",
    student_questions: "AI 同学提问",
    assistant_answer: "助教提示",
    student_question: "同学提问",
    quiz_push: "随堂测验",
    quiz_submitted: "提交测验",
    summary: "课堂总结",
    class_started: "课堂开始",
    student_joined: "同学入班",
  };
  return map[e?.type] || e?.type || "";
}

function eventText(e: any): string {
  const p = e?.payload || {};
  switch (e?.type) {
    case "slide_start":
      return `第 ${(p.index ?? 0) + 1} 页 · ${p.title || ""}`;
    case "teacher_speak":
      return `${p.title || ""}：${(p.script?.analogy || "").slice(0, 60)}`;
    case "student_questions":
      return (p.questions || []).map((q: any) => q.question).join(" / ").slice(0, 80);
    case "student_question":
      return `${p.nickname || "同学"}：${(p.question || "").slice(0, 60)}`;
    case "assistant_answer":
      return `${p.nickname ? p.nickname + " → " : ""}${(p.reply?.probing_question || "").slice(0, 70)}`;
    case "quiz_push":
      return `${p.kp || ""} · ${p.item_count || 0} 题，满分 ${p.max_score || 0}`;
    case "quiz_submitted":
      return `${p.percent ?? 0}% 正确率`;
    case "summary":
      return (p.text || "").slice(0, 90);
    case "class_started":
      return `课堂码 ${p.class_code || ""} · ${p.lesson_title || ""}`;
    case "student_joined":
      return `${p.nickname || "同学"} 加入了课堂`;
    default:
      return "";
  }
}
</script>

<template>
  <view class="page">
    <view class="hero">
      <text class="hero-title">{{ state?.lesson?.title || joined?.lesson_title || "互动课堂" }}</text>
      <text class="hero-sub">
        {{ state?.lesson?.chapter || "有理数的加减运算" }} · {{ state?.lesson?.grade || "七年级" }}
        <template v-if="state"> · 第 {{ (state.session.current_slide || 0) + 1 }} / {{ state.session.slide_count }} 页</template>
      </text>
      <view class="row" style="margin-top: 18rpx">
        <text class="code-big" style="font-size: 32rpx; padding: 8rpx 18rpx; letter-spacing: 4rpx">
          {{ state?.session?.class_code || joined?.class_code }}
        </text>
        <uni-tag v-if="finished" text="课堂已结束" type="warning" size="small" circle />
        <uni-tag v-else text="进行中" type="success" size="small" circle />
      </view>
    </view>

    <view v-if="error" class="error">{{ error }}</view>
    <view v-if="finished" class="notice">本节课已结束，你仍可以回看讲解、做随堂测验和查看学情报告。</view>

    <view v-if="latestQuiz" class="card">
      <view class="card-title">
        <text>随堂测验</text>
        <uni-tag :text="state?.quiz_submitted ? '已提交' : '待完成'" :type="state?.quiz_submitted ? 'success' : 'warning'" size="small" circle />
      </view>
      <text class="muted" style="display: block; margin-bottom: 18rpx">
        共 5 题，覆盖容易 / 中等 / 较难，题目优先取自参考试卷。
      </text>
      <view v-if="state?.quiz_submitted" class="btn primary" @tap="openReport">查看本次报告</view>
      <view v-else class="btn blue" @tap="goQuiz">去答题</view>
    </view>

    <view v-if="slide" class="card">
      <view class="card-title">
        <text>{{ slide.title }}</text>
        <uni-tag :text="slide.kp" type="primary" size="small" circle />
      </view>
      <text class="label">本页要点</text>
      <text v-for="(b, i) in slide.bullets || []" :key="i" class="bullet">· {{ b }}</text>

      <uni-collapse style="margin-top: 18rpx">
        <uni-collapse-item v-if="script.analogy" title="生活类比" :open="true">
          <view class="script-block">
            <text class="script-text">{{ script.analogy }}</text>
          </view>
        </uni-collapse-item>
        <uni-collapse-item v-if="(script.derivation_steps || []).length" title="分步推导">
          <view class="script-block">
            <text v-for="(s, i) in script.derivation_steps" :key="i" class="script-text">{{ i + 1 }}. {{ s }}</text>
          </view>
        </uni-collapse-item>
        <uni-collapse-item v-if="(script.pitfalls || []).length" title="易错点 / 反例">
          <view class="script-block">
            <text v-for="(s, i) in script.pitfalls" :key="i" class="script-text">✗ {{ s }}</text>
          </view>
        </uni-collapse-item>
        <uni-collapse-item v-if="script.exam_application" title="真题应用">
          <view class="script-block">
            <text class="script-text">{{ script.exam_application }}</text>
          </view>
        </uni-collapse-item>
      </uni-collapse>

      <view v-if="(slide.exam_anchors || []).length" style="margin-top: 22rpx">
        <text class="label">本页配套题目（不含答案，先自己想一想）</text>
        <view v-for="item in slide.exam_anchors" :key="item.id" class="script-block" style="border-left-color: #1f5fb4">
          <text class="script-text">{{ item.stem }}</text>
          <view class="row" style="margin-top: 10rpx">
            <uni-tag :text="difficultyLabel(item.difficulty)" :type="difficultyTagType(item.difficulty)" size="small" circle />
            <uni-tag
              :text="item.source_type === 'reference_paper' ? '参考试卷' : '教材改编'"
              :type="item.source_type === 'reference_paper' ? 'success' : 'default'"
              size="small"
              circle
            />
          </view>
        </view>
      </view>
    </view>

    <view v-else class="card">
      <uni-load-more v-if="loading" status="loading" :content-text="{ contentrefresh: '正在同步课堂…' }" />
      <view v-else class="empty">等待老师开始讲解…</view>
    </view>

    <view class="card">
      <view class="card-title">
        <text>向助教提问</text>
        <text class="muted">先给提示，不直接给答案</text>
      </view>
      <textarea
        v-model="question"
        class="textarea"
        maxlength="300"
        placeholder="比如：(-8)+3 为什么等于 -5？我是先算 8+3 的…"
      />
      <view v-if="pickedImage" class="row" style="margin-top: 14rpx">
        <uni-tag text="已选择图片" type="success" size="small" circle />
        <text class="muted" @tap="pickedImage = ''">移除</text>
      </view>
      <view class="row" style="margin-top: 18rpx">
        <view class="btn" style="flex: 1" @tap="chooseImage">拍题上传</view>
        <view class="btn primary" style="flex: 1" :class="{ disabled: asking }" @tap="ask">
          {{ asking ? "助教思考中…" : "发送提问" }}
        </view>
      </view>

      <view v-if="askResult" class="reply">
        <view class="row">
          <uni-tag :text="`提示 ${(askResult.hint_level || 0) + 1} / 4`" type="primary" size="small" circle />
          <text class="muted">再追问一次，会得到更具体的提示</text>
        </view>
        <text v-if="askResult.reply?.probing_question" class="reply-q">{{ askResult.reply.probing_question }}</text>
        <text v-if="askResult.reply?.analogy" class="script-text" style="margin-top: 10rpx">
          类比：{{ askResult.reply.analogy }}
        </text>
        <text v-for="(s, i) in askResult.reply?.steps || []" :key="i" class="script-text">{{ i + 1 }}. {{ s }}</text>
        <text v-if="askResult.reply?.final_answer" class="reply-final">{{ askResult.reply.final_answer }}</text>
      </view>
    </view>

    <view class="card">
      <view class="card-title">
        <text>课堂动态</text>
        <view class="row" @tap="load">
          <uni-icons type="refreshempty" size="16" color="#4c5a72" />
          <text class="muted">刷新</text>
        </view>
      </view>
      <view v-if="!events.length" class="empty">还没有动态，等老师开始上课。</view>
      <view v-for="e in events" :key="e.seq" class="event">
        <view class="row">
          <uni-tag :text="eventLabel(e)" :type="eventTagType(e)" size="small" circle />
        </view>
        <text class="event-text">{{ eventText(e) }}</text>
      </view>
    </view>

    <view class="row" style="margin-top: 8rpx">
      <view class="btn ghost" style="flex: 1" @tap="load">{{ loading ? "刷新中…" : "刷新课堂" }}</view>
      <view class="btn ghost" style="flex: 1" @tap="goMe">我的学情</view>
    </view>
  </view>
</template>

<style scoped>
.bullet {
  display: block;
  font-size: 26rpx;
  line-height: 1.8;
  color: #4c5a72;
}

.reply {
  background: #fbf8f1;
  border-radius: 20rpx;
  padding: 22rpx;
  margin-top: 22rpx;
}

.reply-q {
  display: block;
  font-size: 28rpx;
  font-weight: 700;
  line-height: 1.7;
  margin-top: 12rpx;
  color: #16233a;
}

.reply-final {
  display: block;
  margin-top: 14rpx;
  padding: 16rpx 18rpx;
  background: #fff7d6;
  border-radius: 14rpx;
  font-size: 25rpx;
  line-height: 1.7;
  color: #8a5b13;
}

.event {
  padding: 14rpx 0;
  border-bottom: 2rpx solid rgba(22, 35, 58, 0.06);
}

.event:last-child {
  border-bottom: none;
}

.event-text {
  display: block;
  font-size: 25rpx;
  line-height: 1.7;
  color: #4c5a72;
  margin-top: 8rpx;
}
</style>
