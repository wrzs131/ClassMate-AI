# ClassMate AI 课堂助教平台

面向中小学交互式课堂的多智能体 AI 助教平台：**Vue3 + Element Plus + uni-app + FastAPI + LangChain + Chroma + 硅基流动 Qwen3-VL + MCP工具**。
以教师为中心，覆盖「课件辅助生成 → 课堂互动答疑 → 随堂测验批改 → 学情诊断」完整闭环。
教师端内置 **MCP 工具助手**：用一句自然语言即可查询、新增、修改、删除课件 / 题库 / 课堂 / 学情数据。

---

## 1. 与 OpenMAIC 的差异

| OpenMAIC 的痛点 | 本平台的做法 |
| --- | --- |
| 课件题目不全面、过于简单，缺少真题 | **RAG 真题库** + **Grounding Validator**：题目只能取自已入库的 `exam_items`，禁止模型编造出处；参考试卷题优先，代码层强制易/中/难配比（模型只挑简单题也会被兜底） |
| 讲解偏理论、学生听不懂 | 每页讲稿固定为**四段式**：生活类比 → 分步推导 → 易错点/反例 → 真题应用；可在教师端逐页编辑 |
| 只会套理论，实际做题还是不会 | **苏格拉底式分级提示 L0~L3**（首轮不直接给答案）+ **步骤级批改**（错因归类、掌握度 EMA）+ **同知识点真题推荐** + **学情画像** |

账号体系为「**账号 + 密码登录**」，学生再输入 **6 位课堂码**入班（课堂码唯一、仅进行中的课堂有效）。

---

## **2.功能一览**

### 教师端（Web）

| 模块        | 能力                                                         |
| ----------- | ------------------------------------------------------------ |
| 登录 / 注册 | 账号密码登录，教师与学生角色隔离                             |
| 备课工作台  | 输入学科、年级、教材版本、章节 → 生成课件；每页含四段式讲稿、题锚点（难度 + 来源）、RAG 引用片段；支持逐页编辑、导出 PPTX / JSON |
| 授课控制台  | 一键开课并生成 6 位课堂码；「下一步（多智能体推进）」可选同时推送随堂测验；实时课堂看板（学生数 / 提交数 / 平均得分率 / 知识点掌握 / 错因分布）；生成课堂总结；关闭课堂并用同一课件开启下一堂；历史课堂归档 |
| 学情诊断    | 班级概览、知识点掌握条、错因分布、学生画像与最近作答明细、推荐练习 |
| 知识库      | 知识空间管理、教材 / 试卷上传、参考试卷题导入、语义检索、题库来源与解析查看 |
| AI 助手（MCP） | 独立标签页；开启「MCP 工具模式」后用一句话调用 16 个 MCP 工具：查询课件 / 课堂 / 题库 / 学情与班级报告，新建知识空间、导入真题、修改课件页、开课 / 关课、删除题目 / 文档 / 课件；删除需二次确认；历史对话按教师账号分组保存，可切换、可删除 |

### 学生端（小程序 / H5）

| 模块        | 能力                                                         |
| ----------- | ------------------------------------------------------------ |
| 登录 / 注册 | 账号密码登录                                                 |
| 首页        | 输入 6 位课堂码入班；按账号隔离保存「加入的课堂」；课堂已关闭 / 已结束状态自动校验 |
| 互动课堂    | 当前页讲稿（生活类比 / 分步推导 / 易错点 / 真题应用）；文字提问或**拍照提问**（Qwen3-VL 识图）；分级提示逐层展开；随堂测验入口 |
| 随堂测验    | 选择 / 填空题作答、答题进度、交卷秒回                        |
| 答题报告    | 得分与正确率、逐题步骤反馈与错因、知识点掌握度、推荐同知识点真题 |
| 我的学情    | 个人认知画像、薄弱知识点与练习建议                           |

------

## 3. 技术栈

- 后端：FastAPI、SQLite（标准库 sqlite3，WAL）、PBKDF2 密码 + Bearer Token；运行环境为 **Anaconda 虚拟环境 Python 3.13.12**
- 模型：LangChain `ChatOpenAI` / `OpenAIEmbeddings` → 硅基流动 OpenAI 兼容接口
  - 对话/图片识别：`Qwen/Qwen3-VL-32B-Instruct`（支持学生拍题上传，base64 识图）
  - 嵌入：`Qwen/Qwen3-Embedding-8B`（1024 维）
- 检索：Chroma（`langchain_chroma`，按知识空间独立 collection）；**默认关闭**，自动降级为关键词 bigram 检索，功能不缺失
- 网页端：`web/`（**Vue3 + Vite + TypeScript + Element Plus** 教师工作台，全量注册 `el-*` 组件并覆盖主题变量）
- 小程序端：`fronted/`（**uni-app（Vue3）+ uni-ui** 学生端，`pages.json` 配置 easycom，`uni-icons / uni-tag / uni-easyinput / uni-collapse / uni-load-more`；可编译 H5 / 微信小程序）
- 实时：教师端 SSE（`/api/classroom/{id}/stream`）+ 学生端 5 秒轮询
- MCP：`FastMCP` 注册 16 个工具，以 Streamable HTTP 挂载在 `/mcp`；页面内助手通过 `fastmcp` Client 同进程调用，模型侧走 OpenAI function calling（同时兼容 Qwen3-VL 的 `<tool_call>` 文本协议）
- 导出：python-pptx 生成 PPTX（讲稿写入备注页）

---

## 4. 目录结构

```
├── backend/                 # FastAPI 后端
│   ├── app/
│   │   ├── api/             # 路由：auth / rag / courseware / classroom / quiz / diagnosis / settings / assistant
│   │   ├── services/        # rag / courseware / classroom / quiz / question_bank / diagnosis / event_bus
│   │   ├── agents.py        # 六个智能体：备课 / 教师 / 学生 / 助教 / 批改 / 诊断（含离线确定性脚本）
│   │   ├── mcp_server.py    # MCP Server：16 个工具（查询 8 / 写入 5 / 删除 3），挂载 /mcp
│   │   ├── agent.py         # AI 助手编排：拉取工具 → 模型选工具 → 执行 → 总结，含删除二次确认
│   │   ├── llm.py           # 硅基流动客户端 + JSON 契约修复
│   │   ├── db.py            # 建表 / 轻量迁移（WAL）
│   │   ├── security.py      # PBKDF2 密码 + Bearer Token
│   │   ├── schemas.py       # 请求与响应契约
│   │   ├── json_utils.py    # 答案等价判定（分数 / 多解「或」/ 多空）
│   │   ├── seed.py          # 首次启动写入演示数据
│   │   └── main.py
│   ├── seed/                # 教材片段 + 44 道题（含 OCR 参考试卷题）
│   ├── scripts/             # 自检与演示脚本（含 smoke_mcp.py）
│   ├── tests/               # pytest 后端测试（23 项）
│   ├── requirements.txt
│   ├── run.py
│   └── .env.example         # 环境变量模板
├── web/                     # 教师端（Vue3 + Element Plus）
├── fronted/                 # 学生端（uni-app + uni-ui）
├── docs/                    # 电子课本与参考试卷截图、 OCR 结果
├── fronted-UI/              # README 截图
└── .gitignore
```

---

## 5. 快速启动

### 5.1 后端（Anaconda + Python 3.13）

```powershell
cd backend
conda activate langchain1.2          # 已装好的 Python 3.13.12 环境
python -m pip install -r requirements.txt
copy .env.example .env              # 填写 api_key
python run.py
```

- 服务地址：`http://127.0.0.1:8001`，接口文档：`http://127.0.0.1:8001/docs`
- MCP 端点：`http://127.0.0.1:8001/mcp`（Streamable HTTP），教师端「AI 助手」页同进程调用；`/api/health` 会返回 `mcp` 字段
- 首次启动会自动建表并写入演示数据：3 个知识空间、53 个检索片段、44 道题、演示账号
- 演示账号：`teacher / demo123456`（王老师）、`student / demo123456`（小明）、`student2 / demo123456`（小红）
- 重置数据：停止服务后删除 `backend/storage/app.db*`

### 5.2 教师端（网页：Vue3 + Element Plus）

```powershell
cd web
npm install         # 已包含 element-plus
npm run dev        # http://localhost:5173，/api 已代理到 8001
npm run build      # vue-tsc --noEmit + vite build，产物在 web/dist
```

- 顶部标签页：备课工作台 / 授课控制台 / 学情诊断 / 知识库 / **AI 助手（MCP 工具）**

### 5.3 学生端（小程序：uni-app + uni-ui）

```powershell
cd fronted
npm install         # 已包含 @dcloudio/uni-ui 与 sass
npm run dev:h5     # 浏览器调试（端口被占用时 Vite 会自动换端口）
npm run build:h5   # 产物在 fronted/dist/build/h5
npm run build:mp-weixin   # 产物在 fronted/dist/build/mp-weixin
```

- uni-ui 通过 `src/pages.json` 的 `easycom` 自动引入，页面里直接写 `<uni-icons>` / `<uni-tag>` / `<uni-easyinput>` 等组件即可
- 学生端默认接口地址 `http://127.0.0.1:8001/api`，可在登录页里修改并持久化
- 微信小程序：在 `fronted/src/manifest.json` 填入 `mp-weixin.appid` 后用微信开发者工具导入 `dist/build/mp-weixin`（开发工具需勾选「不校验合法域名」）

---

## 6. 演示流程（约 8 分钟）

### **6.1 流程**

1. 浏览器打开教师端，用 `teacher / demo123456` 登录
2. 「备课工作台」→ 生成课件（默认《有理数的加减运算》，10 道题锚点）
   - 查看每页：四段式讲稿、题锚点难度与来源、RAG 引用的教材片段
   - 可编辑任意一页的标题/要点/讲稿，导出 PPTX / JSON
3. 「授课控制台」→ 选择课件开课，得到 **6 位课堂码**
4. 学生端登录 `student / demo123456` → 首页输入课堂码入班
5. 教师端点「下一步」（可勾选「同时推送随堂测验」），学生端会自动刷新当前页讲稿与题目
6. 学生端可「拍题上传」或文字提问：首轮只给提示与追问，再次追问才逐步给步骤，最后才给结论
7. 教师端点「下一步并推题」→ 学生端出现测验入口 → 学生答题交卷
8. 学生端自动跳转批改报告：得分、逐题反馈、错因、掌握度、推荐练习
9. 教师端「学情诊断」查看班级平均、知识点掌握条、错因分布、学生画像；「授课控制台」点「生成总结」
10. 教师端「知识库」可上传教材/试卷并检索，或查看题库来源与答案解析
11. 教师端「AI 助手」→ 保持「MCP 工具模式」，输入「列出我所有的课件」或「最近一堂课的学情怎么样」，回复下方会显示本次调用的 MCP 工具标签；说「删掉 xxx 课件」会弹出二次确认，确认后才真正执行；右侧可切换 / 删除历史对话

### **6.2 页面图片**

#### Web端（教师端）

#### 登录页

![1](./fronted-UI/web/1.png)

#### 注册页

![1](./fronted-UI/web/2.png)

#### 备课工作台页

![1](./fronted-UI/web/3.png)

导出PPT并查看（讲稿里有真题应用，PPT可优化）

![1](./fronted-UI/web/4.png)

![1](./fronted-UI/web/5.png)

#### 授课控制台页

在备课工作台页选择好课件后，来到授课控制台页即可开始上课（也可以选择历史课堂来上课）

![1](./fronted-UI/web/6.0.png)

![1](./fronted-UI/web/6.png)

学生进入课堂

![1](./fronted-UI/web/6.1.png)

AI教师、AI学生、AI助教互动（根据当前PPT页面互动，待教师讲解完可点击“下一步（多智能体推进）”以跳转到下一页讲解）

![1](./fronted-UI/web/6.2.png)

![1](./fronted-UI/web/6.3.png)

课堂总结（教师可提前结束PPT）

![1](./fronted-UI/web/7.png)

![1](./fronted-UI/web/7.1.png)

![1](./fronted-UI/web/7.1.2.png)

课堂结束后，可以选择仅关闭课堂或者关闭并开启下一堂

![1](./fronted-UI/web/7.2.png)

如果选择关闭并开启下一堂，则会自动根据上一堂课的课件来开课

![1](./fronted-UI/web/7.3.png)

#### 学情诊断页

![1](./fronted-UI/web/8.png)

![1](./fronted-UI/web/8.1.png)

#### 知识库页

![1](./fronted-UI/web/9.png)

#### AI助手页（可正常对话或调用MCP工具做增删改查功能）

![1](./fronted-UI/web/10.png)

正常对话（没有调用MCP工具时）

![1](./fronted-UI/web/10.1.0.png)

调用MCP工具（查）

![1](./fronted-UI/web/10.1.png)

调用MCP工具（改）

![1](./fronted-UI/web/10.2.png)

![1](./fronted-UI/web/10.2.1.png)

调用MCP工具（删）

![1](./fronted-UI/web/10.3.png)

#### 小程序端（学生端）

#### 登录页

![1](./fronted-UI/uniapp/1.png)

#### 注册页

![1](./fronted-UI/uniapp/2.png)

#### 首页

![1](./fronted-UI/uniapp/3.png)

#### 互动课堂页

![1](./fronted-UI/uniapp/4.png)

学生向AI助教提问问题

![1](./fronted-UI/uniapp/4.1.png)

AI助教会先给提示，直到4次提示后才给出答案（分级提示：先给追问与类比，逐步给出步骤，最后才给结论）

![1](./fronted-UI/uniapp/4.2.png)

教师发布随堂测验

![1](./fronted-UI/uniapp/5.png)

#### 随堂测验页

![1](./fronted-UI/uniapp/5.1.png)

提交随堂测验

![1](./fronted-UI/uniapp/5.1.2.png)

#### 答题报告页

![1](./fronted-UI/uniapp/5.2.png)

![1](./fronted-UI/uniapp/5.3.png)

![1](./fronted-UI/uniapp/5.3.2.png)

![1](./fronted-UI/uniapp/5.4.png)

课堂结束

![1](./fronted-UI/uniapp/6.png)

![1](./fronted-UI/uniapp/6.1.png)

#### 我的学情页

个人画像与练习建议，掌握良好

![1](./fronted-UI/uniapp/7.png)

待加强

![1](./fronted-UI/uniapp/7.1.png)

---

## 7. 关键设计

### 7.1 多智能体

`backend/app/agents.py`：Courseware / Teacher / Student / Assistant / Grader / Diagnostician。
后端状态机决定「谁在什么时候说什么」，模型只在固定 JSON 契约内生成；模型不可用时全部退回确定性教学脚本，保证离线可演示。

### 7.2 防编造（Grounding）

- 备课只允许引用检索到的教材 `chunk_id` 与题库 `exam_item_id`
- `_normalize_llm_draft` 会剔除不存在的题目 id；`_balance_difficulties` 强制补齐易/中/难
- 题目保留 `source` 与 `source_type`：`reference_paper`（参考试卷）/ `sample_adapted`（教材改编示例）

### 7.3 引导式答疑

`classroom_service.ask` 按该生在本节课的提问次数递增 `hint_level`（0→3）：
L0 只给追问与类比，L1/L2 逐步给步骤，L3 才给最终结论与完整示范。

### 7.4 判分与学情

- `json_utils.answers_equal`：选择题字母、数值/分数等价、多空同序、**多解题「或」顺序无关**
- `quiz_service`：步骤级反馈 + 错因归类（符号错误 / 计算失误 / 未作答 / 答案不一致）+ 掌握度 EMA（难题权重更高）
- `question_bank.recommend_similar`：同知识点、优先真题、优先中等难度

### 7.5 实时课堂

- 教师端 SSE：`GET /api/classroom/{id}/stream?token=...`（事件总线 + 1s 心跳）
- 学生端轮询 `GET /api/classroom/{id}/state`（5s），兼容小程序
- 事件类型：`slide_start / teacher_speak / student_questions / assistant_answer / student_question / quiz_push / quiz_submitted / summary`

### 7.6 MCP 工具助手

- **工具层**：`backend/app/mcp_server.py` 用 `FastMCP` 注册 16 个工具（查询 8 / 写入 5 / 删除 3），以 Streamable HTTP 挂载在 `/mcp`，与 FastAPI 共用 lifespan
  - 查询：知识检索、题库、课件列表 / 详情、课堂列表、课堂看板、班级报告、学生画像
  - 写入：新建知识空间、导入真题、修改课件页、开课、关课
  - 删除：删除题目、删除知识库文档、删除课件
- **编排**：`backend/app/agent.py` 用 `fastmcp` Client 拉取工具 schema，交给模型 function calling，最多 6 轮「选工具 → 执行 → 结果回填 → 总结」；模型不返回原生 `tool_calls` 时（如 Qwen3-VL）自动解析 `<tool_call>{...}</tool_call>` 文本协议
- **权限与安全**：接口仅教师可用；删除操作走 `confirm_token` + 5 分钟 TTL 二次确认；被测验 / 课堂引用的题目、文档、课件禁止删除；每次调用写入 `mcp_audit_logs` 审计表
- **时间与数据**：工具返回前将毫秒时间戳统一格式化为北京时间，避免模型自行换算日期；提示词要求时间、人数、分数等数据必须直接引用工具结果
- **历史对话**：`assistant_conversations` + `assistant_messages` 按教师账号隔离存储，支持会话切换与删除；离线（无 api_key）时降级为关键词直调查询工具

---

## 8. 数据来源与标注

- `docs/2026北师大版七年级上册数学期中测试卷(含答案).txt` 为图片型文本，已用 Qwen3-VL OCR 到 `docs/exam_pages/ocr/`
- 教材库使用**课标对齐的片段**，支持后台上传替换为其他教材
- 参考试卷题标注 `source_type=reference_paper`，`source=2026北师大版七上期中测试卷（网络参考）`
- 为补齐难度与知识点覆盖，另有教材改编示例题 `sample_adapted`

---

## 9. 配置说明（`backend/.env`）

| 键 | 说明 |
| --- | --- |
| `api_key` | 硅基流动密钥（`sk-` 开头），缺失则自动离线演示 |
| `model_name` / `embedding_model` | 默认 `Qwen/Qwen3-VL-32B-Instruct` / `Qwen/Qwen3-Embedding-8B` |
| `request_timeout` | 单次调用超时，整份课件 JSON 建议 240~300 秒 |
| `use_llm` | `false` 时全部走确定性脚本（答辩断网也可用） |
| `enable_vector` | Chroma 开关，默认 `false`；关闭时检索自动降级为关键词 bigram |
| `host` / `port` | 默认 `0.0.0.0:8001` |

### 关于 Chroma 依赖

`requirements.txt` 面向 **Python 3.13**（没有 numpy 1.x 的 wheel），因此固定为：

```
langchain-chroma>=1.1.0
chromadb>=1.5.9
numpy>=2.1
```

本机实测：`chromadb` 执行 `add` 时可能触发底层崩溃（`numpy 2.x` 与 `chroma-hnswlib` 的 ABI 不兼容，退出码 `0xC0000005`）。
由于 `rag_service` 只在 `enable_vector=true` 时才导入 `langchain_chroma`，**默认 `false` 不影响启动与其它功能**，检索自动降级为关键词 bigram。

装好后先自检（子进程隔离，崩溃不会带走主服务）：

```powershell
conda activate langchain1.2
python scripts\check_vector.py
```

通过后再把 `.env` 的 `enable_vector` 改为 `true`。未通过时保持 `false`，所有功能仍可用。

---

## 10. 测试与自检脚本

```powershell
cd backend
conda activate langchain1.2
python -m pytest tests -q                     # 23 项：鉴权/备课/检索/课堂/测验/学情/判分/MCP
python scripts\smoke_e2e.py                   # 离线端到端冒烟（输出 SMOKE OK）
python scripts\smoke_mcp.py                   # MCP 冒烟：工具列举 → 建库 → 导题 → 查询 → 删除
python scripts\live_check.py                  # 真实 uvicorn 进程联调（健康/登录/备课/开课/SSE）
python scripts\check_llm.py                   # 真实模型 + 嵌入连通性
python scripts\check_courseware_llm.py        # 真实模型生成整份课件
python scripts\check_vector.py                # Chroma 子进程探针
```

前端自检：

```powershell
cd web && npm run build                      # vue-tsc + vite build
cd fronted && npm run type-check && npm run build:h5 && npm run build:mp-weixin
```

---

## 11. 已知限制

- 向量检索默认关闭（依赖本机二进制环境），关键词检索已覆盖演示所需
- 小程序端需自行填写 appid；H5 端已验证构建与类型检查
- 板书/公式以文本形式呈现（LaTeX 渲染暂未接入）
