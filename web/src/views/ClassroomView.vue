<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { api, getApiBase, getToken } from "../api";
import { rememberLesson, rememberSession, state as app } from "../store";

const lessons = ref<any[]>([]);
const sessions = ref<any[]>([]);
const sessionId = ref(app.sessionId);
const classroom = ref<any>(null);
const dashboard = ref<any>(null);
const events = ref<any[]>([]);
const includeQuiz = ref(true);
const busy = ref(false);
const error = ref("");
const summary = ref("");
const stream = ref<EventSource | null>(null);
const loading = ref(false);

const currentSlide = computed(() => classroom.value?.current_slide || null);
const latestQuiz = computed(() => classroom.value?.latest_quiz || null);
const slideCount = computed(() => classroom.value?.session?.slide_count || 0);
const currentIndex = computed(() => classroom.value?.session?.current_slide || 0);
const closing = ref(false);

const sessionStatus = computed<string>(() => classroom.value?.session?.status || "");
const isActive = computed(() => sessionStatus.value === "active");
const activeSessions = computed(() => sessions.value.filter((item) => item.status === "active"));
const historySessions = computed(() => sessions.value.filter((item) => item.status !== "active"));

function statusLabel(status: string): string {
  if (status === "active") return "进行中";
  if (status === "closed") return "已关闭";
  return "已结束";
}

function statusTagType(status: string): "success" | "warning" | "info" {
  if (status === "active") return "success";
  if (status === "closed") return "info";
  return "warning";
}

/** 给教师看的随堂测验提示：只讲「提交了多少人 / 平均分」，不暴露内部 id 与状态字段。 */
const quizNotice = computed<{ type: "info" | "success" | "warning"; title: string } | null>(() => {
  if (!latestQuiz.value) return null;
  const stats = (dashboard.value?.quizzes || []).find((item: any) => item.id === latestQuiz.value.id)?.stats;
  const submitted = Number(stats?.attempts || 0);
  const total = Number(classroom.value?.students?.length || 0);
  const average = Number(stats?.average || 0);
  if (!submitted) return { type: "info", title: "最近一次随堂测验已推送，等待学生提交…" };
  if (total > 0 && submitted >= total) {
    return { type: "success", title: `最近一次随堂测验：全班 ${total} 人已提交（平均得分率 ${average}%）` };
  }
  return { type: "info", title: `最近一次随堂测验：已有 ${submitted}${total ? `/${total}` : ""} 人提交` };
});

const kpMastery = computed(() => dashboard.value?.kp_mastery || []);
const errorCounts = computed(() => {
  const counts = dashboard.value?.error_counts || {};
  return Object.entries(counts).sort((a: any, b: any) => b[1] - a[1]);
});

function tagClass(type: string) {
  if (type.startsWith("assistant")) return "assistant";
  if (type.startsWith("student")) return "student";
  if (type.startsWith("teacher") || type.startsWith("quiz")) return "teacher";
  return "system";
}

function timelineType(type: string): "primary" | "success" | "warning" | "danger" | "info" {
  if (type.startsWith("assistant")) return "success";
  if (type.startsWith("student")) return "warning";
  if (type.startsWith("teacher") || type.startsWith("quiz")) return "primary";
  return "info";
}

function eventLabel(type: string): string {
  const map: Record<string, string> = {
    class_started: "开课",
    student_joined: "学生入班",
    student_left: "学生退班",
    slide_start: "进入幻灯片",
    teacher_speak: "教师讲解",
    student_questions: "AI 学生会问",
    student_question: "学生提问",
    assistant_answer: "助教答疑",
    quiz_push: "推送随堂测验",
    quiz_submitted: "学生提交",
    summary: "课堂总结",
    class_closed: "关闭课堂",
  };
  return map[type] || type;
}

async function loadBasics() {
  loading.value = true;
  try {
    const [lessonData, sessionData] = await Promise.all([api.listLessons(), api.listSessions()]);
    lessons.value = lessonData.lessons || [];
    sessions.value = sessionData.sessions || [];
    if (!app.lessonId && lessons.value[0]) rememberLesson(lessons.value[0].id);
  } catch (err: any) {
    error.value = err?.message || "加载失败";
  } finally {
    loading.value = false;
  }
}

async function openSession(id: string) {
  sessionId.value = id;
  rememberSession(id);
  error.value = "";
  summary.value = "";
  closeStream();
  try {
    await refreshState(true);
    await refreshDashboard();
    openStream();
  } catch (err: any) {
    error.value = err?.message || "打开课堂失败";
    // 无权访问（例如课堂属于其他账号）：清掉缓存并回到开课面板
    if (err?.status === 403 || String(error.value).includes("无权")) {
      rememberSession("");
      sessionId.value = "";
      classroom.value = null;
      dashboard.value = null;
      events.value = [];
    }
  }
}

async function refreshState(reset = false) {
  if (!sessionId.value) return;
  const afterSeq = reset ? 0 : events.value.length ? events.value[events.value.length - 1].seq : 0;
  classroom.value = await api.getState(sessionId.value, afterSeq);
  if (reset) events.value = classroom.value.events || [];
  else {
    const incoming = classroom.value.events || [];
    const known = new Set(events.value.map((e) => e.seq));
    events.value.push(...incoming.filter((e: any) => !known.has(e.seq)));
  }
}

async function refreshDashboard() {
  if (!sessionId.value) return;
  try {
    dashboard.value = await api.dashboard(sessionId.value);
  } catch {
    dashboard.value = null;
  }
}

async function createSession() {
  if (!app.lessonId) {
    error.value = "请先在备课工作台生成课件";
    return;
  }
  busy.value = true;
  error.value = "";
  try {
    const data = await api.createSession(app.lessonId);
    await loadBasics();
    await openSession(data.session.id);
    await refreshState(true);
  } catch (err: any) {
    error.value = err?.message || "开课失败";
  } finally {
    busy.value = false;
  }
}

async function advance() {
  if (!sessionId.value) return;
  busy.value = true;
  error.value = "";
  try {
    const data = await api.advance(sessionId.value, includeQuiz.value);
    if (data?.done) {
      summary.value = data.summary || "本课已结束";
    }
    await refreshState();
    await refreshDashboard();
  } catch (err: any) {
    error.value = err?.message || "推进失败";
  } finally {
    busy.value = false;
  }
}

async function makeSummary() {
  if (!sessionId.value) return;
  busy.value = true;
  try {
    const data = await api.summary(sessionId.value);
    summary.value = data.summary;
    await refreshState();
  } catch (err: any) {
    error.value = err?.message || "生成总结失败";
  } finally {
    busy.value = false;
  }
}

function openStream() {
  if (!sessionId.value) return;
  closeStream();
  if (typeof EventSource === "undefined") return;
  const after = events.value.length ? events.value[events.value.length - 1].seq : 0;
  const url = `${getApiBase()}/classroom/${sessionId.value}/stream?after_seq=${after}&token=${encodeURIComponent(getToken())}`;
  const source = new EventSource(url);
  source.onmessage = (evt) => {
    try {
      const data = JSON.parse(evt.data);
      if (!events.value.some((item) => item.seq === data.seq)) events.value.push(data);
      // 入班/退班/关课这类事件还会改变成员列表与课堂状态，需要同步刷新 state，
      // 否则「学生 N 人」与成员列表会一直停留在旧数据
      if (["student_joined", "student_left", "class_started", "class_closed"].includes(data.type)) {
        refreshState().catch(() => undefined);
      }
      refreshDashboard();
    } catch {
      /* 忽略心跳 */
    }
  };
  source.onerror = () => {
    /* 断流时靠手动刷新兜底，避免频繁重连 */
  };
  stream.value = source;
}

function closeStream() {
  if (stream.value) {
    stream.value.close();
    stream.value = null;
  }
}

async function copyCode() {
  if (!classroom.value?.session?.class_code) return;
  const code = classroom.value.session.class_code;
  try {
    await navigator.clipboard.writeText(code);
    ElMessage.success(`课堂码 ${code} 已复制`);
  } catch {
    ElMessage.info(`课堂码：${code}`);
  }
}

function eventPlain(event: any): string {
  const p = event.payload || {};
  switch (event.type) {
    case "class_started":
      return `课堂码 ${p.class_code}，课件《${p.lesson_title}》`;
    case "student_joined":
      return `${p.nickname} 加入课堂`;
    case "student_left":
      return `${p.nickname} 退出课堂`;
    case "slide_start":
      return `第 ${Number(p.index) + 1}/${p.total} 页：${p.title}`;
    case "quiz_push":
      return `已推送 ${p.item_count} 道题（${p.kp}，满分 ${p.max_score}）`;
    case "quiz_submitted":
      return `${p.score}/${p.max_score} 分（${p.percent}%）`;
    case "class_closed":
      return "本课已关闭，课堂码失效";
    default:
      return "";
  }
}

function updateNow() {
  refreshState();
  refreshDashboard();
}

/**
 * 关闭当前课堂（归档）：课堂码立即失效，数据仍保留在「学情诊断」。
 * next = "panel"：回到开课面板；next = "restart"：关闭后用当前课件直接开下一堂。
 */
async function closeClass(next: "panel" | "restart") {
  if (!sessionId.value) return;
  try {
    await ElMessageBox.confirm(
      "关闭后本课堂的课堂码立即失效，学生无法再通过该课堂码加入；课堂数据会保留在「学情诊断」。",
      "关闭当前课堂",
      { confirmButtonText: "关闭课堂", cancelButtonText: "取消", type: "warning" }
    );
  } catch {
    return;
  }
  closing.value = true;
  error.value = "";
  try {
    await api.closeSession(sessionId.value);
    closeStream();
    rememberSession("");
    sessionId.value = "";
    classroom.value = null;
    dashboard.value = null;
    events.value = [];
    summary.value = "";
    await loadBasics();
    ElMessage.success("课堂已关闭，可重新开课");
    if (next === "restart") await createSession();
  } catch (err: any) {
    error.value = err?.message || "关闭课堂失败";
  } finally {
    closing.value = false;
  }
}

onMounted(async () => {
  await loadBasics();
  // 本地缓存的课堂可能属于上一个登录账号：不在当前教师的课堂列表里就不再自动打开
  if (sessionId.value && !sessions.value.some((item) => item.id === sessionId.value)) {
    rememberSession("");
    sessionId.value = "";
  }
  if (sessionId.value) await openSession(sessionId.value);
});

onBeforeUnmount(closeStream);
</script>

<template>
  <div v-if="!classroom" v-loading="loading" class="card">
    <div class="card-title">
      <h3>授课控制台</h3>
      <span class="sub">开课后学生用 6 位课堂码入班</span>
    </div>
    <p class="muted">
      当前课件：{{ lessons.find((item) => item.id === app.lessonId)?.title || "未选择（请先去备课工作台生成/选择）" }}
    </p>
    <div class="row" style="margin-top: 12px">
      <el-button type="primary" :loading="busy" @click="createSession">开始上课</el-button>
      <el-button @click="updateNow">刷新</el-button>
    </div>
    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon style="margin-top: 12px" />
    <div v-if="activeSessions.length" class="divider"></div>
    <div v-if="activeSessions.length">
      <p class="muted" style="margin-bottom: 8px">继续进行中的课堂</p>
      <div class="lesson-list" style="max-height: 220px">
        <button v-for="item in activeSessions" :key="item.id" class="lesson-item" @click="openSession(item.id)">
          <b>{{ item.lesson_title }}</b>
          <span>课堂码 {{ item.class_code }} · 进行中 · {{ new Date(item.created_at).toLocaleString() }}</span>
        </button>
      </div>
    </div>
    <div v-if="historySessions.length" class="divider"></div>
    <div v-if="historySessions.length">
      <p class="muted" style="margin-bottom: 8px">历史课堂（已结束 / 已关闭，仅存档查看）</p>
      <div class="lesson-list" style="max-height: 220px">
        <button v-for="item in historySessions" :key="item.id" class="lesson-item" @click="openSession(item.id)">
          <b>{{ item.lesson_title }}</b>
          <span>
            课堂码 {{ item.class_code }} · {{ statusLabel(item.status) }} ·
            {{ new Date(item.created_at).toLocaleString() }}
          </span>
        </button>
      </div>
    </div>
  </div>

  <div v-else class="classroom">
    <section>
      <div class="card">
        <div class="class-code">
          <div>
            <span class="muted">课堂码（学生登录后输入）</span>
            <div class="code-big">{{ classroom.session.class_code }}</div>
          </div>
          <div style="flex: 1">
            <div class="row" style="gap: 8px; margin-bottom: 8px">
              <el-tag effect="light" round>{{ classroom.lesson.title }}</el-tag>
              <el-tag :type="statusTagType(classroom.session.status)" effect="light" round>
                {{ statusLabel(classroom.session.status) }}
              </el-tag>
              <el-tag type="success" effect="light" round>学生 {{ classroom.students?.length || 0 }} 人</el-tag>
              <el-tag type="warning" effect="light" round>第 {{ currentIndex + 1 }}/{{ slideCount }} 页</el-tag>
            </div>
            <div class="row">
              <el-button type="primary" class="is-blue" :loading="busy" :disabled="!isActive" @click="advance">
                下一步（多智能体推进）
              </el-button>
              <el-checkbox v-model="includeQuiz" :disabled="!isActive">同时推送随堂测验</el-checkbox>
              <el-button :disabled="busy || sessionStatus === 'closed'" @click="makeSummary">生成课堂总结</el-button>
              <el-button size="small" @click="copyCode">复制课堂码</el-button>
              <el-button size="small" link type="primary" @click="updateNow">刷新</el-button>
            </div>
            <div class="row" style="margin-top: 8px">
              <el-button
                v-if="isActive"
                size="small"
                type="danger"
                plain
                :loading="closing"
                @click="closeClass('panel')"
              >
                关闭当前课堂
              </el-button>
              <template v-else>
                <el-button size="small" type="primary" :loading="closing" @click="closeClass('restart')">
                  关闭并开启下一堂
                </el-button>
                <el-button size="small" :loading="closing" @click="closeClass('panel')">仅关闭课堂</el-button>
              </template>
            </div>
            <el-alert
              v-if="!isActive"
              :type="sessionStatus === 'closed' ? 'info' : 'warning'"
              :closable="false"
              show-icon
              style="margin-top: 12px"
              :title="
                sessionStatus === 'closed'
                  ? '本课已关闭：课堂码已失效。点「关闭并开启下一堂」用当前课件开新课堂，或回到开课面板重新选课件。'
                  : '本课已结束（课堂总结已生成）。关闭课堂后即可用同一课件开启下一堂，课堂码会重新生成。'
              "
            />
          </div>
        </div>
        <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon style="margin-top: 12px" />

        <el-alert
          v-if="quizNotice"
          :type="quizNotice.type"
          :closable="false"
          show-icon
          style="margin-top: 12px"
          :title="quizNotice.title"
        />
        <div v-if="summary" class="script-box" style="margin-top: 12px">
          <b style="font-size: 11px; color: var(--blue)">课堂总结</b>
          <p style="margin: 6px 0 0; font-size: 12.5px; line-height: 1.8">{{ summary }}</p>
        </div>
      </div>

      <div class="card">
        <div class="card-title">
          <h3>当前幻灯片</h3>
          <span class="sub">{{ currentSlide?.kp }}</span>
        </div>
        <div v-if="currentSlide" class="class-now">
          <h4>{{ currentSlide.title }}</h4>
          <p>{{ (currentSlide.bullets || []).join(" ｜ ") }}</p>
        </div>
        <el-empty v-else description="还没有开始讲解，点击「下一步」" :image-size="56" />

        <div v-if="currentSlide" class="script-box">
          <div class="script-4">
            <div>
              <b>生活类比</b>
              <p>{{ currentSlide.script?.analogy || "—" }}</p>
            </div>
            <div>
              <b>分步推导</b>
              <p>{{ (currentSlide.script?.derivation_steps || []).join(" → ") || "—" }}</p>
            </div>
            <div>
              <b>易错点 / 反例</b>
              <p>{{ (currentSlide.script?.pitfalls || []).join("；") || "—" }}</p>
            </div>
            <div>
              <b>真题应用</b>
              <p>{{ currentSlide.script?.exam_application || "—" }}</p>
            </div>
          </div>
        </div>

        <div v-if="currentSlide?.exam_anchors?.length" class="anchor-list">
          <span v-for="anchor in currentSlide.exam_anchors" :key="anchor.id" class="anchor" :title="anchor.analysis">
            <b>{{ anchor.id }}</b> {{ anchor.stem.slice(0, 40) }}…
          </span>
        </div>
      </div>

      <div class="card">
        <div class="card-title">
          <h3>课堂事件流</h3>
          <span class="sub">SSE 实时推送 · 可逐条追溯</span>
        </div>
        <el-empty v-if="!events.length" description="暂无事件，点击「下一步」开始" :image-size="56" />
        <div v-else class="timeline">
          <el-timeline>
            <el-timeline-item
              v-for="event in events"
              :key="event.seq"
              :type="timelineType(event.type)"
              :timestamp="`#${event.seq}`"
              placement="top"
            >
              <div class="event" :class="tagClass(event.type)">
                <div class="event-head">
                  <b>{{ eventLabel(event.type) }}</b>
                </div>
                <p v-if="eventPlain(event)" class="event-body">{{ eventPlain(event) }}</p>

                <template v-if="event.type === 'teacher_speak'">
                  <div class="script-4">
                    <div>
                      <b>生活类比</b>
                      <p>{{ event.payload.script?.analogy }}</p>
                    </div>
                    <div>
                      <b>分步推导</b>
                      <p>{{ (event.payload.script?.derivation_steps || []).join(" → ") }}</p>
                    </div>
                    <div>
                      <b>易错点</b>
                      <p>{{ (event.payload.script?.pitfalls || []).join("；") }}</p>
                    </div>
                  </div>
                </template>

                <template v-if="event.type === 'student_questions'">
                  <ul class="event-body">
                    <li v-for="(q, idx) in event.payload.questions || []" :key="idx">
                      {{ q.question }} <span class="muted">（{{ q.misconception }}）</span>
                    </li>
                  </ul>
                </template>

                <template v-if="event.type === 'student_question'">
                  <p class="event-body">{{ event.payload.nickname }}：{{ event.payload.question }}</p>
                </template>

                <template v-if="event.type === 'assistant_answer'">
                  <p class="event-body">
                    提示级别 L{{ event.payload.reply?.hint_level }} ·
                    {{ event.payload.reply?.probing_question || "—" }}
                  </p>
                  <ul class="event-body">
                    <li v-for="(step, idx) in event.payload.reply?.steps || []" :key="idx">{{ step }}</li>
                  </ul>
                </template>
              </div>
            </el-timeline-item>
          </el-timeline>
        </div>
      </div>
    </section>

    <aside>
      <div class="card">
        <div class="card-title">
          <h3>课堂看板</h3>
          <span class="sub">实时</span>
        </div>
        <div class="stat-row">
          <div class="stat">
            <el-statistic :value="dashboard?.student_count ?? 0" title="学生" />
          </div>
          <div class="stat">
            <el-statistic :value="dashboard?.submissions ?? 0" title="提交" />
          </div>
          <div class="stat">
            <el-statistic :value="dashboard?.average ?? 0" suffix="%" title="平均分" />
          </div>
        </div>

        <div class="divider"></div>
        <div class="card-title">
          <span class="sub" style="font-weight: 600; color: var(--ink)">知识点掌握度</span>
        </div>
        <el-empty v-if="!kpMastery.length" description="暂无提交数据" :image-size="48" />
        <div v-for="item in kpMastery" :key="item.kp" class="kp-bar">
          <span :title="item.kp">{{ item.kp }}</span>
          <el-progress
            :percentage="Math.round(item.average * 100)"
            :stroke-width="8"
            :show-text="false"
            :status="item.average < 0.6 ? 'warning' : 'success'"
          />
          <em>{{ Math.round(item.average * 100) }}%</em>
        </div>

        <div class="divider"></div>
        <div class="card-title">
          <span class="sub" style="font-weight: 600; color: var(--ink)">错因分布</span>
        </div>
        <el-empty v-if="!errorCounts.length" description="暂无错题" :image-size="48" />
        <div v-for="[name, count] in errorCounts" :key="name" class="row" style="justify-content: space-between; margin-bottom: 6px">
          <el-tag type="danger" effect="light" round>{{ name }}</el-tag>
          <span class="muted">{{ count }} 次</span>
        </div>
      </div>

      <div class="card">
        <div class="card-title">
          <h3>学生</h3>
          <span class="sub">课堂码入班</span>
        </div>
        <el-empty v-if="!classroom.students?.length" description="等待学生输入课堂码…" :image-size="48" />
        <div v-for="student in classroom.students" :key="student.id" class="doc-row">
          <div>
            <b>{{ student.nickname }}</b>
            <span> · {{ student.username }}</span>
          </div>
          <el-tag type="success" effect="light" round>已入班</el-tag>
        </div>
      </div>

      <div v-if="dashboard?.recent?.length" class="card">
        <div class="card-title">
          <h3>最近提交</h3>
        </div>
        <el-table :data="dashboard.recent" size="small" style="width: 100%">
          <el-table-column prop="student" label="学生" />
          <el-table-column label="得分" width="90">
            <template #default="{ row }">{{ row.score }}/{{ row.max_score }}</template>
          </el-table-column>
          <el-table-column prop="percent" label="正确率" width="80">
            <template #default="{ row }">{{ row.percent }}%</template>
          </el-table-column>
        </el-table>
      </div>
    </aside>
  </div>
</template>
