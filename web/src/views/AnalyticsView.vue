<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { api } from "../api";
import { rememberSession, state as app } from "../store";

const sessions = ref<any[]>([]);
const sessionId = ref(app.sessionId);
const dashboard = ref<any>(null);
const student = ref<any>(null);
const error = ref("");
const loading = ref(false);

const kpMastery = computed(() => dashboard.value?.kp_mastery || []);
const errorCounts = computed(() => {
  const counts = dashboard.value?.error_counts || {};
  return Object.entries(counts).sort((a: any, b: any) => b[1] - a[1]);
});
const studentMastery = computed(() => student.value?.mastery || []);
const recommended = computed(() => student.value?.recommended || []);

async function loadSessions() {
  const data = await api.listSessions();
  sessions.value = data.sessions || [];
  // 换账号后本地缓存的课堂可能属于别的老师：先校验归属，失效则回退到自己的第一堂
  if (sessionId.value && !sessions.value.some((item) => item.id === sessionId.value)) {
    rememberSession("");
    sessionId.value = "";
  }
  if (!sessionId.value && sessions.value[0]) sessionId.value = sessions.value[0].id;
}

let retriedFallback = false;

async function loadDashboard() {
  if (!sessionId.value) return;
  loading.value = true;
  error.value = "";
  student.value = null;
  try {
    dashboard.value = await api.dashboard(sessionId.value);
    rememberSession(sessionId.value);
    retriedFallback = false;
  } catch (err: any) {
    error.value = err?.message || "加载学情失败";
    const denied = err?.status === 403 || String(error.value).includes("无权");
    if (denied && !retriedFallback) {
      // 缓存的课堂不属于当前账号：自动切到自己课堂列表里的第一堂
      const fallback = sessions.value.find((item) => item.id !== sessionId.value);
      rememberSession("");
      sessionId.value = fallback ? fallback.id : "";
      if (sessionId.value) {
        retriedFallback = true;
        await loadDashboard();
        return;
      }
    }
  } finally {
    loading.value = false;
  }
}

async function openStudent(id: string) {
  try {
    student.value = await api.studentDiagnosis(id);
  } catch (err: any) {
    error.value = err?.message || "加载学生学情失败";
  }
}

function progressStatus(score: number): "success" | "warning" | "exception" {
  if (score < 0.4) return "exception";
  if (score < 0.6) return "warning";
  return "success";
}

onMounted(async () => {
  try {
    await loadSessions();
    await loadDashboard();
  } catch (err: any) {
    error.value = err?.message || "加载失败";
  }
});
</script>

<template>
  <div v-loading="loading" class="card">
    <div class="card-title">
      <div>
        <h3>学情诊断</h3>
        <span class="sub">班级掌握度 · 错因分布 · 学生画像 · 同知识点真题推荐</span>
      </div>
      <div class="row">
        <el-select v-model="sessionId" placeholder="选择课堂" style="width: 320px" @change="loadDashboard">
          <el-option value="" disabled label="选择课堂" />
          <el-option
            v-for="item in sessions"
            :key="item.id"
            :value="item.id"
            :label="`${item.lesson_title}（${item.class_code}）`"
          />
        </el-select>
        <el-button size="small" @click="loadDashboard">刷新</el-button>
      </div>
    </div>
    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />
    <el-empty v-if="!sessions.length" description="还没有课堂数据，先去授课控制台开课" :image-size="56" />
  </div>

  <div v-if="dashboard" class="grid grid-2" style="margin-top: 16px">
    <div class="card">
      <div class="card-title">
        <h3>班级概览</h3>
        <span class="sub">课堂码 {{ dashboard.class_code }}</span>
      </div>
      <div class="stat-row">
        <div class="stat">
          <el-statistic :value="dashboard.student_count" title="入班学生" />
        </div>
        <div class="stat">
          <el-statistic :value="dashboard.submissions" title="提交人次" />
        </div>
        <div class="stat">
          <el-statistic :value="dashboard.average" suffix="%" title="平均正确率" />
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
          :status="progressStatus(item.average)"
        />
        <em>{{ Math.round(item.average * 100) }}%</em>
      </div>
    </div>

    <div class="card">
      <div class="card-title">
        <h3>错因分布</h3>
        <span class="sub">批改智能体自动归类</span>
      </div>
      <el-empty v-if="!errorCounts.length" description="还没有错题记录" :image-size="48" />
      <div v-for="[name, count] in errorCounts" :key="name" class="kp-bar">
        <span>{{ name }}</span>
        <el-progress
          :percentage="Math.min(100, Number(count) * 12)"
          :stroke-width="8"
          :show-text="false"
          status="exception"
        />
        <em>{{ count }}</em>
      </div>

      <div class="divider"></div>
      <div class="card-title">
        <span class="sub" style="font-weight: 600; color: var(--ink)">最近提交</span>
      </div>
      <el-table :data="dashboard.recent || []" size="small" style="width: 100%">
        <el-table-column prop="student" label="学生" />
        <el-table-column label="得分" width="90">
          <template #default="{ row }">{{ row.score }}/{{ row.max_score }}</template>
        </el-table-column>
        <el-table-column label="正确率" width="80">
          <template #default="{ row }">{{ row.percent }}%</template>
        </el-table-column>
        <template #empty>
          <el-empty description="暂无提交" :image-size="44" />
        </template>
      </el-table>
    </div>
  </div>

  <div v-if="dashboard" class="card" style="margin-top: 16px">
    <div class="card-title">
      <h3>学生画像</h3>
      <span class="sub">点击学生查看个人学情与推荐题</span>
    </div>
    <div class="space-list">
      <el-check-tag
        v-for="item in dashboard.students"
        :key="item.id"
        :checked="student?.student?.id === item.id"
        style="margin-right: 8px"
        @change="openStudent(item.id)"
      >
        {{ item.nickname }}
      </el-check-tag>
    </div>
    <el-empty v-if="!dashboard.students?.length" description="暂无学生，学生端用课堂码入班后出现" :image-size="56" />

    <div v-if="student" style="margin-top: 8px">
      <div class="row" style="justify-content: space-between">
        <div>
          <b style="font-size: 15px">{{ student.student?.nickname }}</b>
          <span class="muted"> · {{ student.student?.username }}</span>
        </div>
        <el-tag :type="student.weak_points?.length ? 'danger' : 'success'" effect="light" round>
          {{ student.weak_points?.length ? `薄弱：${student.weak_points.join("、")}` : "掌握稳定" }}
        </el-tag>
      </div>
      <el-alert :title="student.summary" type="warning" :closable="false" show-icon style="margin: 10px 0" />

      <div v-for="row in studentMastery" :key="row.kp" class="kp-bar">
        <span>{{ row.kp }}</span>
        <el-progress
          :percentage="Math.round(row.score * 100)"
          :stroke-width="8"
          :show-text="false"
          :status="progressStatus(row.score)"
        />
        <em>{{ Math.round(row.score * 100) }}%</em>
      </div>

      <div class="divider"></div>
      <div class="card-title">
        <span class="sub" style="font-weight: 600; color: var(--ink)">最近作答</span>
        <span class="sub">{{ student.attempts?.length || 0 }} 条</span>
      </div>
      <el-table :data="student.attempts || []" size="small" style="width: 100%">
        <el-table-column label="题目" min-width="220">
          <template #default="{ row }">{{ row.stem?.slice(0, 46) }}…</template>
        </el-table-column>
        <el-table-column prop="kp" label="知识点" width="150" />
        <el-table-column label="结果" width="80">
          <template #default="{ row }">
            <el-tag :type="row.correct ? 'success' : 'danger'" effect="light" round>
              {{ row.correct ? "正确" : "错误" }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="错因" width="110">
          <template #default="{ row }">{{ row.error_type || "—" }}</template>
        </el-table-column>
        <template #empty>
          <el-empty description="暂无作答记录" :image-size="44" />
        </template>
      </el-table>

      <div class="divider"></div>
      <div class="card-title">
        <span class="sub" style="font-weight: 600; color: var(--ink)">推荐练习（同知识点真题优先）</span>
      </div>
      <el-empty v-if="!recommended.length" description="暂无推荐" :image-size="48" />
      <div v-for="item in recommended" :key="item.id" class="search-hit">
        <div class="row" style="justify-content: space-between">
          <b style="font-size: 12.5px">{{ item.stem }}</b>
          <el-tag type="info" effect="light" round>{{ item.id }}</el-tag>
        </div>
        <p>
          知识点 {{ item.kp }} ·
          {{ item.difficulty === "easy" ? "容易" : item.difficulty === "hard" ? "较难" : "中等" }} ·
          {{ item.source_type === "reference_paper" ? "参考试卷" : "示例改编" }} · {{ item.source }}
        </p>
      </div>
    </div>
  </div>
</template>
