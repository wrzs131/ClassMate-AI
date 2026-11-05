<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import type { UploadFile } from "element-plus";
import { ElMessage } from "element-plus";
import { api } from "../api";

const spaces = ref<any[]>([]);
const activeSpace = ref("");
const documents = ref<any[]>([]);
const exams = ref<any[]>([]);
const total = ref(0);
const stats = ref<any>(null);
const kp = ref("");
const difficulty = ref("");
const uploading = ref(false);
const error = ref("");
const notice = ref("");
const searchQuery = ref("异号相加 绝对值");
const searchKind = ref("textbook");
const hits = ref<any[]>([]);

const activeSpaceInfo = computed(() => spaces.value.find((item) => item.id === activeSpace.value));
const kpOptions = [
  "有理数的概念",
  "有理数的加法",
  "有理数的减法",
  "有理数加减混合运算",
  "相反数与倒数",
  "数轴与绝对值",
  "有理数加减应用",
];
const difficultyOptions = [
  { label: "容易", value: "easy" },
  { label: "中等", value: "medium" },
  { label: "较难", value: "hard" },
];

async function loadSpaces() {
  const data = await api.spaces();
  spaces.value = data.spaces || [];
  if (!activeSpace.value && spaces.value.length) activeSpace.value = spaces.value[0].id;
  await loadDocuments();
}

async function loadDocuments() {
  if (!activeSpace.value) return;
  try {
    const data = await api.documents(activeSpace.value);
    documents.value = data.documents || [];
  } catch (err: any) {
    documents.value = [];
  }
}

async function loadExams() {
  try {
    const data = await api.exams({ kp: kp.value || undefined, difficulty: difficulty.value || undefined, limit: 100 });
    exams.value = data.items || [];
    total.value = data.total || 0;
  } catch (err: any) {
    error.value = err?.message || "加载题库失败";
  }
}

async function loadStats() {
  try {
    stats.value = await api.ragStats();
  } catch {
    stats.value = null;
  }
}

async function onFileChange(file: UploadFile) {
  const raw = file.raw;
  if (!raw || !activeSpace.value) return;
  uploading.value = true;
  error.value = "";
  notice.value = "";
  try {
    const doc = await api.upload(activeSpace.value, raw);
    notice.value = `已入库：${doc.name}（${doc.chunk_count} 个片段）`;
    ElMessage.success("文档已入库");
    await loadDocuments();
    await loadStats();
  } catch (err: any) {
    error.value = err?.message || "上传失败";
  } finally {
    uploading.value = false;
  }
}

async function search() {
  if (!searchQuery.value.trim()) return;
  error.value = "";
  try {
    const data = await api.search({
      query: searchQuery.value,
      kind: searchKind.value || null,
      top_k: 6,
    });
    hits.value = data.hits || [];
  } catch (err: any) {
    error.value = err?.message || "检索失败";
  }
}

function sourceTag(type: string) {
  return type === "reference_paper" ? "success" : "warning";
}

function sourceText(type: string) {
  return type === "reference_paper" ? "参考试卷" : "示例改编";
}

function difficultyType(value: string) {
  return value === "easy" ? "success" : value === "hard" ? "danger" : "warning";
}

function difficultyText(value: string) {
  return value === "easy" ? "容易" : value === "hard" ? "较难" : "中等";
}

onMounted(async () => {
  try {
    await Promise.all([loadSpaces(), loadExams(), loadStats()]);
  } catch (err: any) {
    error.value = err?.message || "加载失败";
  }
});
</script>

<template>
  <div class="card">
    <div class="card-title">
      <div>
        <h3>知识库</h3>
        <span class="sub">教材 / 课标 / 参考试卷 · 所有题目可溯源</span>
      </div>
      <div v-if="stats" class="row" style="gap: 6px">
        <el-tag effect="light" round>文档 {{ stats.documents }}</el-tag>
        <el-tag effect="light" round>片段 {{ stats.chunks }}</el-tag>
        <el-tag type="success" effect="light" round>题目 {{ stats.exam_items }}</el-tag>
        <el-tag type="info" effect="light" round>
          向量检索：{{ stats.spaces?.length ? "关键词降级" : "—" }}
        </el-tag>
      </div>
    </div>

    <div class="space-list">
      <button
        v-for="space in spaces"
        :key="space.id"
        class="space-chip"
        :class="{ active: activeSpace === space.id }"
        @click="activeSpace = space.id; loadDocuments()"
      >
        {{ space.name }}
        <el-tag type="info" effect="light" round style="margin-left: 6px">{{ space.kind }}</el-tag>
      </button>
    </div>

    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />
    <el-alert v-if="notice" :title="notice" type="success" :closable="false" show-icon />

    <div class="grid grid-2">
      <div>
        <div class="card-title">
          <span class="sub" style="font-weight: 600; color: var(--ink)">
            {{ activeSpaceInfo?.name || "文档" }}
          </span>
          <el-upload
            :auto-upload="false"
            :show-file-list="false"
            accept=".pdf,.docx,.txt,.md"
            :on-change="onFileChange"
          >
            <el-button size="small" :loading="uploading">上传 PDF/DOCX/TXT/MD</el-button>
          </el-upload>
        </div>
        <p class="muted" style="margin: 0 0 8px">{{ activeSpaceInfo?.description }}</p>
        <el-empty v-if="!documents.length" description="该空间还没有文档" :image-size="48" />
        <div v-for="doc in documents" :key="doc.id" class="doc-row">
          <div>
            <b>{{ doc.name }}</b>
            <span> · {{ doc.chunk_count }} 片段 · {{ doc.file_type }}</span>
          </div>
          <el-tag :type="doc.embedded ? 'success' : 'info'" effect="light" round>
            {{ doc.embedded ? "已向量化" : "关键词检索" }}
          </el-tag>
        </div>
      </div>

      <div>
        <div class="card-title">
          <span class="sub" style="font-weight: 600; color: var(--ink)">检索调试</span>
          <span class="sub">教师可查看题目/讲解的引用来源</span>
        </div>
        <div class="row" style="margin-bottom: 8px">
          <el-input v-model="searchQuery" style="flex: 1" placeholder="例如：异号相加 绝对值" @keyup.enter="search" />
          <el-select v-model="searchKind" style="width: 120px">
            <el-option label="全部" value="" />
            <el-option label="教材" value="textbook" />
            <el-option label="题库" value="exam" />
            <el-option label="课标" value="standard" />
          </el-select>
          <el-button size="small" type="primary" @click="search">检索</el-button>
        </div>
        <el-empty v-if="!hits.length" description="输入关键词查看命中的教材片段 / 题目" :image-size="48" />
        <div v-for="hit in hits" :key="hit.chunk_id" class="search-hit">
          <div class="row" style="justify-content: space-between">
            <el-tag type="info" effect="light" round>{{ hit.chunk_id || hit.kind }}</el-tag>
            <span class="muted">相关度 {{ (hit.score * 100).toFixed(0) }}% · {{ hit.source }}</span>
          </div>
          <p>{{ hit.content.slice(0, 220) }}{{ hit.content.length > 220 ? "…" : "" }}</p>
        </div>
      </div>
    </div>
  </div>

  <div class="card" style="margin-top: 16px">
    <div class="card-title">
      <div>
        <h3>题库</h3>
        <span class="sub">参考试卷题优先，示例改编题用于补齐难度分层 · 共 {{ total }} 道</span>
      </div>
      <div class="row">
        <el-select v-model="kp" placeholder="全部知识点" clearable style="width: 190px" @change="loadExams">
          <el-option v-for="item in kpOptions" :key="item" :value="item" :label="item" />
        </el-select>
        <el-select v-model="difficulty" placeholder="全部难度" clearable style="width: 120px" @change="loadExams">
          <el-option v-for="item in difficultyOptions" :key="item.value" :value="item.value" :label="item.label" />
        </el-select>
        <el-button size="small" @click="loadExams">刷新</el-button>
      </div>
    </div>

    <el-table :data="exams" row-key="id" size="small" style="width: 100%">
      <el-table-column type="expand">
        <template #default="{ row }">
          <div class="notice" style="margin: 0 12px 8px">
            <b>答案：</b>{{ row.answer }}<br />
            <b>解析：</b>{{ row.analysis || "—" }}
          </div>
        </template>
      </el-table-column>
      <el-table-column prop="id" label="编号" width="130">
        <template #default="{ row }">
          <span style="font-family: var(--mono); font-size: 10.5px">{{ row.id }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="kp" label="知识点" width="150" />
      <el-table-column label="难度" width="80">
        <template #default="{ row }">
          <el-tag :type="difficultyType(row.difficulty)" effect="light" round>{{ difficultyText(row.difficulty) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="stem" label="题干" min-width="240" show-overflow-tooltip />
      <el-table-column label="来源" width="130">
        <template #default="{ row }">
          <el-tag :type="sourceTag(row.source_type)" effect="light" round>{{ sourceText(row.source_type) }}</el-tag>
          <div class="muted" style="margin-top: 4px">{{ row.source }}</div>
        </template>
      </el-table-column>
      <template #empty>
        <el-empty description="暂无题目" :image-size="48" />
      </template>
    </el-table>
  </div>
</template>
