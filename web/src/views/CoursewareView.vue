<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { api } from "../api";
import { rememberLesson, state } from "../store";

const lessons = ref<any[]>([]);
const lesson = ref<any>(null);
const loading = ref(false);
const generating = ref(false);
const error = ref("");
const saveTip = ref("");
const savingSlide = ref("");

const form = reactive({
  subject: "数学",
  grade: "七年级",
  textbook_version: "北师大版（2026）",
  chapter: "有理数的加减运算",
  exam_count: 10,
  easy: 3,
  medium: 2,
  hard: 1,
  use_llm: true,
});

const coverage = computed(() => lesson.value?.exam_coverage || {});
const difficultyText = computed(() => {
  const d = coverage.value.difficulty || {};
  return `易 ${d.easy || 0} · 中 ${d.medium || 0} · 难 ${d.hard || 0}`;
});

async function loadLessons(selectId?: string) {
  const data = await api.listLessons();
  lessons.value = data.lessons || [];
  const target = selectId || state.lessonId || lessons.value[0]?.id;
  if (target) {
    const found = lessons.value.find((item) => item.id === target);
    if (found) await openLesson(found.id);
  }
}

async function openLesson(id: string) {
  try {
    lesson.value = await api.getLesson(id);
    rememberLesson(id);
    saveTip.value = "";
  } catch (err: any) {
    error.value = err?.message || "加载课件失败";
  }
}

async function generate() {
  error.value = "";
  generating.value = true;
  try {
    const created = await api.generate({
      subject: form.subject,
      grade: form.grade,
      textbook_version: form.textbook_version,
      chapter: form.chapter,
      exam_count: form.exam_count,
      difficulty_mix: { easy: form.easy, medium: form.medium, hard: form.hard },
      use_llm: form.use_llm,
    });
    lesson.value = created;
    rememberLesson(created.id);
    await loadLessons(created.id);
  } catch (err: any) {
    error.value = err?.message || "生成失败";
  } finally {
    generating.value = false;
  }
}

async function saveSlide(slide: any) {
  if (!lesson.value) return;
  savingSlide.value = slide.id;
  saveTip.value = "";
  try {
    await api.patchSlide(lesson.value.id, slide.id, {
      title: slide.title,
      bullets: slide.bullets,
      script: slide.script,
    });
    saveTip.value = `已保存：${slide.title}`;
    setTimeout(() => (saveTip.value = ""), 2500);
  } catch (err: any) {
    error.value = err?.message || "保存失败";
  } finally {
    savingSlide.value = "";
  }
}

function addBullet(slide: any) {
  slide.bullets.push("补充要点…");
}

function removeBullet(slide: any, idx: number) {
  slide.bullets.splice(idx, 1);
}

function splitSteps(text: string): string[] {
  return text
    .split(/\n|；/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function setList(target: any, key: string, text: string) {
  target[key] = splitSteps(text);
}

async function exportFile(format: "pptx" | "json") {
  if (!lesson.value) return;
  try {
    const blob = await api.exportLesson(lesson.value.id, format);
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${lesson.value.title}.${format}`;
    a.click();
    URL.revokeObjectURL(url);
  } catch (err: any) {
    error.value = err?.message || "导出失败";
  }
}

function difficultyTag(value: string) {
  return value === "easy" ? "success" : value === "hard" ? "danger" : "warning";
}

function sourceLabel(item: any) {
  return item?.source_type === "reference_paper" ? "参考试卷" : "示例改编";
}

onMounted(async () => {
  loading.value = true;
  try {
    await loadLessons();
  } catch (err: any) {
    error.value = err?.message || "加载失败";
  } finally {
    loading.value = false;
  }
});
</script>

<template>
  <div class="workspace">
    <aside>
      <div v-loading="generating" class="card">
        <div class="card-title">
          <h3>备课参数</h3>
          <span class="sub">真题优先组卷</span>
        </div>
        <el-form label-position="top">
          <el-form-item label="章节">
            <el-input v-model="form.chapter" />
          </el-form-item>
          <div class="grid grid-2">
            <el-form-item label="学科">
              <el-input v-model="form.subject" />
            </el-form-item>
            <el-form-item label="年级">
              <el-input v-model="form.grade" />
            </el-form-item>
          </div>
          <el-form-item label="教材版本">
            <el-input v-model="form.textbook_version" />
          </el-form-item>
          <el-form-item :label="`题目数量：${form.exam_count} 道（6–14）`">
            <el-slider v-model="form.exam_count" :min="6" :max="14" :step="1" show-stops />
          </el-form-item>
          <div class="grid grid-3">
            <el-form-item label="易">
              <el-input-number v-model="form.easy" :min="0" :max="5" controls-position="right" style="width: 100%" />
            </el-form-item>
            <el-form-item label="中">
              <el-input-number v-model="form.medium" :min="0" :max="5" controls-position="right" style="width: 100%" />
            </el-form-item>
            <el-form-item label="难">
              <el-input-number v-model="form.hard" :min="0" :max="5" controls-position="right" style="width: 100%" />
            </el-form-item>
          </div>
        </el-form>

        <el-checkbox v-model="form.use_llm" style="margin-bottom: 6px">
          使用 Qwen3-VL 生成讲稿（关闭则走内置四段式脚本）
        </el-checkbox>
        <p v-if="form.use_llm" class="sub" style="margin: 0 0 12px; font-size: 11px">
          真实模型生成整份课件约需 1~3 分钟，请勿关闭页面；若超时或失败会自动回退到内置脚本。
        </p>
        <el-button type="primary" style="width: 100%" :loading="generating" @click="generate">
          生成课件
        </el-button>
        <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon style="margin-top: 10px" />
      </div>

      <div class="card">
        <div class="card-title">
          <h3>我的课件</h3>
          <span class="sub">{{ lessons.length }} 份</span>
        </div>
        <el-empty v-if="loading" description="加载中…" :image-size="52" />
        <el-empty v-else-if="!lessons.length" description="还没有课件，先生成一份" :image-size="52" />
        <div v-else class="lesson-list">
          <button
            v-for="item in lessons"
            :key="item.id"
            class="lesson-item"
            :class="{ active: lesson?.id === item.id }"
            @click="openLesson(item.id)"
          >
            <b>{{ item.title }}</b>
            <span>{{ item.chapter }} · {{ new Date(item.created_at).toLocaleString() }}</span>
          </button>
        </div>
      </div>
    </aside>

    <section v-if="lesson">
      <div class="card">
        <div class="card-title">
          <div>
            <h3 style="font-size: 18px">{{ lesson.title }}</h3>
            <span class="sub">
              {{ lesson.grade }} · {{ lesson.subject }} · {{ lesson.textbook_version }} ·
              {{ lesson.llm_used ? "Qwen3-VL 生成" : "确定性脚本兜底" }}
            </span>
          </div>
          <div class="row">
            <el-button size="small" @click="exportFile('pptx')">导出 PPTX</el-button>
            <el-button size="small" @click="exportFile('json')">导出 JSON</el-button>
          </div>
        </div>

        <div class="row" style="gap: 6px; margin-bottom: 12px">
          <el-tag v-for="obj in lesson.objectives" :key="obj" effect="light" round>{{ obj }}</el-tag>
        </div>

        <div class="row" style="gap: 10px">
          <el-tag type="success" effect="light" round>题目 {{ coverage.total || 0 }} 道</el-tag>
          <el-tag type="warning" effect="light" round>{{ difficultyText }}</el-tag>
          <el-tag effect="light" round>参考试卷占比 {{ Math.round((coverage.reference_ratio || 0) * 100) }}%</el-tag>
          <el-tag type="info" effect="light" round>{{ lesson.slides.length }} 张幻灯片</el-tag>
        </div>

        <div v-if="lesson.rag_contexts?.length" class="divider"></div>
        <div v-if="lesson.rag_contexts?.length">
          <div class="row" style="justify-content: space-between">
            <span class="sub" style="font-size: 11px; color: var(--ink-mute)">教材检索引用（RAG）</span>
            <el-tag type="info" effect="light" round>{{ lesson.rag_contexts.length }} 条</el-tag>
          </div>
          <div class="anchor-list">
            <span v-for="ctx in lesson.rag_contexts" :key="ctx.chunk_id" class="anchor" :title="ctx.content">
              <b>{{ ctx.chunk_id }}</b> {{ ctx.source }} · {{ (ctx.score * 100).toFixed(0) }}%
            </span>
          </div>
        </div>
        <el-alert v-if="saveTip" :title="saveTip" type="success" :closable="false" show-icon style="margin-top: 12px" />
      </div>

      <div class="card">
        <div class="card-title">
          <h3>幻灯片与讲稿</h3>
          <span class="sub">讲稿固定四段：生活类比 / 分步推导 / 易错点 / 真题应用</span>
        </div>

        <div v-for="(slide, idx) in lesson.slides" :key="slide.id" class="slide-card">
          <div class="slide-head">
            <span class="slide-index">{{ idx + 1 }}</span>
            <el-input v-model="slide.title" size="small" style="flex: 1" />
            <el-tag type="info" effect="light" round>{{ slide.kp }}</el-tag>
            <el-button size="small" :loading="savingSlide === slide.id" @click="saveSlide(slide)">保存</el-button>
          </div>

          <div class="bullets-editor">
            <div v-for="(bullet, bidx) in slide.bullets" :key="bidx" class="bullet-line">
              <el-input v-model="slide.bullets[bidx]" size="small" />
              <el-button size="small" link type="danger" @click="removeBullet(slide, bidx)">删除</el-button>
            </div>
          </div>
          <el-button size="small" link type="primary" @click="addBullet(slide)">+ 添加要点</el-button>

          <div class="script-box">
            <div class="script-4">
              <div>
                <b>生活类比</b>
                <p>{{ slide.script.analogy || "—" }}</p>
              </div>
              <div>
                <b>分步推导</b>
                <p>{{ (slide.script.derivation_steps || []).join(" → ") || "—" }}</p>
              </div>
              <div>
                <b>易错点 / 反例</b>
                <p>{{ (slide.script.pitfalls || []).join("；") || "—" }}</p>
              </div>
              <div>
                <b>真题应用</b>
                <p>{{ slide.script.exam_application || "—" }}</p>
              </div>
            </div>

            <el-collapse style="margin-top: 6px">
              <el-collapse-item title="编辑讲稿" name="script">
                <el-form label-position="top">
                  <el-form-item label="生活类比">
                    <el-input v-model="slide.script.analogy" type="textarea" :rows="2" />
                  </el-form-item>
                  <el-form-item label="分步推导（每行一步）">
                    <el-input
                      :model-value="(slide.script.derivation_steps || []).join('\n')"
                      type="textarea"
                      :rows="3"
                      @update:model-value="setList(slide.script, 'derivation_steps', $event)"
                    />
                  </el-form-item>
                  <el-form-item label="易错点 / 反例（每行一条）">
                    <el-input
                      :model-value="(slide.script.pitfalls || []).join('\n')"
                      type="textarea"
                      :rows="3"
                      @update:model-value="setList(slide.script, 'pitfalls', $event)"
                    />
                  </el-form-item>
                  <el-form-item label="真题应用">
                    <el-input v-model="slide.script.exam_application" type="textarea" :rows="2" />
                  </el-form-item>
                </el-form>
              </el-collapse-item>
            </el-collapse>
          </div>

          <div v-if="slide.exam_anchors?.length" class="anchor-list">
            <span v-for="anchor in slide.exam_anchors" :key="anchor.id" class="anchor" :title="anchor.answer">
              <b>{{ anchor.id }}</b> {{ anchor.kp }}
              <el-tag :type="difficultyTag(anchor.difficulty)" effect="light" round style="margin-left: 6px">
                {{ anchor.difficulty === "easy" ? "易" : anchor.difficulty === "hard" ? "难" : "中" }}
              </el-tag>
              <el-tag type="info" effect="light" round style="margin-left: 4px">{{ sourceLabel(anchor) }}</el-tag>
            </span>
          </div>
        </div>
      </div>
    </section>

    <section v-else class="card">
      <el-empty description="左侧生成或选择一份课件开始编辑" :image-size="72" />
    </section>
  </div>
</template>
