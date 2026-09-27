# ai-knowledge-base

面向研发团队的内部技术文档知识库问答服务。把散落在 Markdown / PDF / Word / HTML 里的技术文档统一入库，提问时检索相关片段、生成**带来源和页码引用**的回答；资料中没有依据的问题明确拒答，不编造。

- 技术栈：Spring Boot 4.1 + Spring AI + PostgreSQL(pgvector) + Redis ｜ HanLP 词典分词 BM25 + BGE-Reranker 精排（独立 FastAPI 服务）
- 语料：**172 篇** —— `knowledge/` 27 篇自建计算机基础文档（Java / Spring / MySQL / Redis / Kubernetes / 网络 / 操作系统等）+ `knowledge-official/` 142 篇抓取的官方文档（Spring、RabbitMQ、Redis 等）+ `test-documents/` 3 篇测试文档（不规则 DOCX / HTML / TXT，用来验证解析容错），覆盖 PDF、DOCX、HTML、Markdown、TXT 五种格式

## 应用场景

**给谁用**：需要查内部技术文档的研发与测试——新人熟悉代码库、老手回忆某个配置项的确切写法、排查问题时确认某个版本下的行为。

**为什么需要**：用通用模型查技术问题有两个让人不放心的地方，这也是本项目的设计重点。

**一、答得不专业，还会编。** 问"这个 Spring Boot 版本下事务的默认传播行为"，通用模型会给一个"听起来对"的答案，而版本差异恰恰是最容易出错的地方。这里要求模型只能基于检索到的文档片段作答，并在回答里标出片段来自哪份文档、哪一页——页码是 PDF 解析阶段就保留的元数据，不是事后拼的。

**二、"查不到"和"没答案"是两回事。** 真正危险的不是答不出，而是资料不足时依然自信作答。这里按精排相关度分数设了拒答阈值（0.60，在 60 条标定子集上校准），检索结果不够相关时直接返回"知识库中没有足够依据"。

**两个关键技术取舍**：

- **双路召回而非纯向量**：纯向量对专有名词不敏感（同一术语的不同写法在向量空间里距离很近），而中文 BM25 按单字切分会把"数据库连接池"误匹配到"连接""接池"。所以用向量 + HanLP 词典分词的 BM25 双路召回，再用 RRF 融合——RRF 只看排名不看分数，绕开了两路分数量纲不可比的问题。
- **精排服务独立部署**：BGE-Reranker 加载慢、占内存，做成独立 FastAPI 服务由 Docker 管理；并做了故障注入验证——精排不可用时自动降级为混合检索结果，整条链路不中断。

## 评测

`evaluation/` 下是 134 条标注验证集（109 条库内 + 25 条库外），9 种检索方案的实测结果（`evaluation_results.json` 可复算）。

**27 篇语料条件下的实测（历史批次，语料 = `knowledge/` 27 篇）**

| 方案 | 文档 R@1 | 文档 R@3 | 章节 R@1 |
|---|---|---|---|
| 纯向量 | 93.6% | 99.1% | 88.5% |
| BM25（HanLP 分词） | 93.6% | 99.1% | 80.2% |
| 混合检索（V5+B5，RRF 融合） | 98.2% | **100%** | 88.5% |
| 混合 + BGE 精排 | 98.2% | **100%** | **90.6%** |

另有：

- `compare_bm25.py`：分词改造前后对比（单字切分 → HanLP 词典分词，**27 篇语料下**章节首位命中率 71.9% → 80.2%）
- 查询扩展实验：实测指标反而略降，未启用，代码保留实验接口
- RRF 候选数敏感性实验（V/B 各取 5 与 10 的 2×2 网格）：结论是不敏感，保留默认公式

### 口径与复算（引用任何数字前先看这节）

语料规模一变，指标的**分母**就变了：语料从 27 篇扩到 172 篇（27 自建 + 142 官方 + 3 测试）后，章节级命中率会整体下移（同一套检索逻辑、同一套题目，章节 R@1 从 80 字头掉到 70 字头是正常的），**跨语料的数字不可比、不可混用**。

- 每次评测都会往 `evaluation/evaluation_runs.jsonl` **追加一行运行记录**：语料条件（`--note`）、验证集规模、各方案指标、推荐阈值。对外引用数字时，必须带上该行里的 `note`。
- 复算命令：

```bash
python evaluation/evaluate.py --note "172 篇：27 自建 + 142 官方 + 3 测试"   # 9 方案横评 + 阈值扫描 + 运行日志
python evaluation/tokenizer_compare_current.py                            # 分词改造前后（当前语料，含"改造前"复测）
python evaluation/check_labels.py                                         # 标注健全性：金标是否在 Top5 内
```

- 上表数字来自 27 篇语料时期；**扩语料后必须重跑**，并以 `evaluation_runs.jsonl` 中的新值为准，不要把两套口径的数字放进同一段表述。

## 快速开始

前置：JDK 17、Docker Desktop、本地 Ollama

```bash
# 1. 起依赖：PostgreSQL(pgvector) + Redis + 精排服务
docker compose up -d

# 2. 准备本地模型（对话 + 嵌入）
ollama pull qwen3:4b && ollama pull bge-m3

# 3. 启动应用（首次启动自动建向量表）
./mvnw spring-boot:run
```

导入语料（三个目录合起来就是 172 篇口径）：

```bash
curl -X POST "http://localhost:8080/api/knowledge/import-all"                          # knowledge/ 27 篇自建
curl -X POST "http://localhost:8080/api/knowledge/import-all?dir=knowledge-official"   # 142 篇官方文档
curl -X POST "http://localhost:8080/api/knowledge/import-all?dir=test-documents"       # 3 篇测试文档
```

## 接口

| 路径 | 说明 |
|---|---|
| `POST /api/knowledge/import` / `import-all` | 导入语料并向量化 |
| `GET /api/knowledge/search` | 纯向量检索 |
| `GET /api/knowledge/bm25-search` | BM25 检索 |
| `GET /api/knowledge/hybrid-search` | 双路召回 + RRF 融合 |
| `GET /api/chat` | 问答，返回 JSON：`answer` / `refused` / `trace_id` / `top1_score` / `threshold` / `policy`；带 `sessionId` 时启用会话记忆，并返回本次实际检索用的 `retrieval_query` 与 `rewritten` |
| `GET /api/chat/session` | 查看某会话的记忆概况（轮数、最近问答、Redis 是否可用） |
| `DELETE /api/chat/session` | 清空某会话的记忆 |
| `POST /api/feedback` | 提交反馈：`trace_id` + `rating`(up/down) + 可选 `expected_source`，负反馈进入自进化闭环 |
| `GET /api/evolution/summary` | 闭环概况（轨迹数 / 拒答数 / 反馈数） |
| `GET /api/evolution/export` | 导出轨迹与反馈，供 `evolution/evolve.py` 归因 |
| `GET /api/chat/policy` | 当前生效的检索策略（阈值 / 候选数 / 精排数 / 来源与时间） |
| `POST /api/chat/policy/reload` | 重新加载策略文件（扫参后无需重启） |
| `GET /api/tool/chat` | 工具调用（检索/文档列表，含精排降级） |
| `GET /api/ai/chat` | 纯模型对话（不检索知识库，对照用） |
| `GET /api/knowledge/rerank-test` | 精排效果对比（可传 `candidateK` / `rerankTopK` 做参数实验） |

交互式提问脚本 `ask.py`（双击 `提问.bat`）已适配新返回结构，支持多轮追问（自动补全指代）、`赞` / `踩 期望文档名` 反馈，以及 `会话` / `新会话` / `清空会话` 三条会话命令。

## 会话记忆（多轮对话）

单轮问答的硬伤：**"它一般设置多长的过期时间？"这类追问检索不到任何东西** —— 指代对象只存在于上一轮对话里。会话记忆把这个问题拆成两步：

```
sessionId ──► ConversationMemoryService（Redis 窗口，最近 5 轮，TTL 30 分钟）
                          │
                          ▼
              QueryRewriteService（指代消解："它" → "Redis 分布式锁"）
                          │
                          ▼  用改写后的问题检索（响应里的 retrieval_query 可验证）
                   Hybrid → Rerank → 拒答 → 生成
                          │
                          ▼
              回写窗口（问题 + 回答摘要 + 命中来源名）
```

三个设计取舍：

- **fail-open 是硬要求**：Redis 不可用时全部操作降级为"无历史对话"，问答照常进行（这个项目在引入 Redis 之前本来就能跑单轮），只在日志里告警；`/api/chat/session` 会显示 `redis_available`，排障时能区分"没记忆"和"没连上"。
- **无历史就不改写**：改写是额外的一次模型调用（本地 7B 约几秒到几十秒），没有历史时无从下手，直接跳过；改写失败也原样回落到原问题，绝不因为改写让问答失败。
- **窗口只存摘要**：助手侧只留回答前 200 字与命中的来源名，避免把整篇回答塞回下一轮的改写提示词；窗口上限 5 轮、TTL 30 分钟，超出丢最旧的（`ConversationMemoryService.Window.appended` 是纯函数，边界行为有单测）。

会话记忆的收益是可测的：`evaluation/memory_eval.py` 对同一条指代追问跑"有记忆 / 无记忆"两臂，比较金标召回率与上下文命中率。

```bash
# 体验两轮：第一轮建立指代对象，第二轮的"它"会被补全
curl "http://localhost:8080/api/chat?question=Redis%20分布式锁怎么实现&sessionId=demo-1" | python -m json.tool
curl "http://localhost:8080/api/chat?question=它一般设置多长的过期时间？&sessionId=demo-1" | python -m json.tool
#   第二次响应里 rewritten=true、retrieval_query 形如 "Redis 分布式锁的过期时间是多少"
# 不带 sessionId 再问一次同一句，检索问题就是原句（无记忆臂）
curl "http://localhost:8080/api/chat?question=它一般设置多长的过期时间？" | python -m json.tool

python evaluation/memory_eval.py --limit 4     # 4 条用例 × 3 次问答调用（开场 / 有记忆 / 无记忆）
python -m pytest evolution/tests -q            # 26 个闭环逻辑用例
./mvnw test -Dtest='ConversationMemoryServiceTest,QueryRewriteServiceTest'   # 13 个 Java 纯逻辑用例
```

## 自进化闭环

把"用户说这条答错了"变成"评测集多一条用例、阈值可自动重标定、下次改动有回归保护"：

```
用户反馈（赞/踩 + 期望来源）──► qa_feedback ─┐
问答轨迹（召回候选 / 精排分数 / 是否拒答）──► qa_trace ─┘
        │
        ├─ evolution/evolve.py      归因失败层 → 评测集生长 + 待人工标注队列
        ├─ evolution/auto_tune.py   标注验证集上扫参选优 → evaluation/selected_policy.json
        ├─ evolution/regression.py  回归门禁：指标回退则非零退出（可挂 CI / 提交前检查）
        └─ 应用启动读取策略文件（RetrievalPolicyService），或 POST /api/chat/policy/reload 热加载
```

```bash
python evolution/evolve.py --api http://localhost:8080 --write   # 归因 + 评测集生长（默认 dry-run）
python evolution/auto_tune.py --limit 40 --write                # 扫参选优 → 策略文件
python evolution/regression.py                                  # 回归门禁（回退则退出码 1）
python evolution/regression.py --update-baseline                # 固化当前指标为新基线
python -m pytest evolution/tests -q                             # 26 个纯逻辑用例（无需数据库）
```

> Python 工具链依赖：`requests`（评测/扫参/门禁的 HTTP 调用）、`pytest`（测试）。`ask.py` 与 `evolve.py` 只用标准库。

三个设计取舍：

- **归因是确定性规则，不是再叫一次 LLM 判断**：依据回答时的检索现场——候选里有没有金标、金标有没有进上下文、是否拒答、引用编号是否越界——定位到召回层 / 精排层 / 阈值层 / 生成层 / 引用层。判错层就等于改错地方。
- **没有金标的负反馈不猜标签**：进 `evaluation/pending_labels.json` 等人工标注。评测集是口径的根，脚本不替人打标。
- **策略文件是唯一出口**：扫参结果写进 `evaluation/selected_policy.json`，应用启动时读取并回落到内置默认值（阈值 0.60 / Top5 / Top3）。阈值与语料分布绑定，换语料必须重标定——这条写进了 `RetrievalPolicyService` 的注释里。

产物文件：

| 文件 | 作用 | 谁写 |
|---|---|---|
| `evaluation/evaluation_runs.jsonl` | 每次评测的运行记录（语料条件 + 指标 + 推荐阈值） | `evaluate.py` 追加 |
| `evaluation/selected_policy.json` | 当前生效的检索策略（应用启动时读取） | `auto_tune.py` |
| `evaluation/baseline_metrics.json` | 回归基线 | `regression.py --update-baseline` |
| `evaluation/evolved_cases.json` | 由 badcase 长出来的评测用例 | `evolve.py --write` |
| `evaluation/pending_labels.json` | 待人工标注的负反馈 | `evolve.py --write` |
| `evaluation/evolution_report.md` | 失败层分布 + 阈值重标定建议 | `evolve.py --write` |
| `evaluation/judge/judge_scores.json` | 逐题生成质量裁判分数 + 上下文 | `judge_eval.py` |
| `evaluation/judge/human_labels.json` | 人工评分（裁判校准锚点，待人工填写） | `human_rate.py` 生成骨架 |
| `evaluation/judge/calibration_report.md` | 裁判与人工的一致率 + 放行结论 | `judge_calibrate.py` |

## 生成质量评测（LLM-as-judge）

检索层与拒答层都有指标，但**回答本身的质量此前没有任何自动指标**。这一层用本地裁判补齐三个维度（对齐 RAGAS 的核心口径，但不出网、可复算）：

- `faithfulness` 忠实度：回答中的事实性陈述是否都能在检索片段里找到依据（= 幻觉检测）
- `relevancy` 切题度：回答是否直接命中问题
- `correctness` 正确性：内容是否正确（评测条目带 `expected_points` 时按要点覆盖评判）

分数 1~5，`>= 4` 为通过。**裁判必须先用人工评分校准**，否则只是一个"不敢信的数字"：

```
人工评分（20~30 条，独立打分）──┐
                                ├─► 一致率校准（相邻一致率 / MAE / kappa）──► 达标才用裁判跑全量
LLM 裁判（同一批回答问题）──────┘
```

裁判与生成用**不同模型**：生成为应用侧的 `qwen3:4b`，裁判默认 `qwen2.5:7b-instruct`（异族 + 异规模，规避"自己评自己"的自偏好偏差；8GB 显存下 7B-Q4 刚好装得下），可用 `--judge-model` 覆盖。

```bash
python evaluation/human_rate.py --limit 20     # 取回答+上下文，生成人工评分表与标签骨架
#   → 评分有两种方式，二选一（人工评分是裁判的校准锚点，必须由人来做）：
#       A) 交互式：python evaluation/human_score.py   （终端逐题显示材料，敲 1~5 即落盘，推荐）
#       B) 手动：在 evaluation/judge/human_labels.json 里填 scores（锚点见 judge/human_rubric.md）
python evaluation/judge_eval.py --limit 20 --note "172 篇：27 自建 + 142 官方 + 3 测试"
#   → evaluation/judge/judge_scores.json + judge_report.md
python evaluation/judge_calibrate.py           # 一致率不达标则退出码 1，禁止采用裁判分数
python -m pytest evaluation/tests -q           # 53 个纯逻辑用例（无需数据库 / Ollama）
```

评测条目可选加 `expected_points`（参考要点，向后兼容，现有脚本不受影响），用于把 correctness 从"裁判自主判断"升级为"要点覆盖"：

```json
{ "query": "多个服务实例如何控制对共享资源的并发访问？", "relevant_source": "redis.md",
  "relevant_section": "Redis 分布式锁",
  "expected_points": ["使用分布式锁实现互斥", "Redis 可以用 SET 命令实现分布式锁",
                      "需要设置过期时间并避免误删他人的锁"] }
```

要点必须**只取金标章节原文支持的范围**——实测中我把 B+Tree 章节的"叶子节点双向链表"塞进了"MySQL 索引"章节的题目要点，裁判据此扣分，制造出 3 条假分歧（详见下文复盘）。

### 实测：两轮校准，把裁判从"不敢信"调到"可用"

口径：172 篇语料、20 条人工标注样本（数据集前 20 条，均库内且被作答）、裁判 `qwen2.5:7b-instruct`、生成 `qwen3:4b`。**样本小且偏易，数字只在这批样本上成立。**

**第一轮**（裁判 prompt 只写了"正确且完整"）——门禁判失败：

| correctness | 数值 |
|---|---|
| MAE | 0.55（> 0.5，未达标） |
| 相邻一致率 | 0.85 |
| 方向性（裁判偏高/人工偏高） | 7 / 1 |

分歧明细显示**裁判系统性偏宽**：7 条它给 5、人工给 3~4。根因不是分数不稳，而是笼统判据让裁判凭"内容出自知识库、且切题"直接给 5，对"答全没答全"完全不敏感。

**两个修复**：

1. prompt 把 correctness 拆成**强制两步**：先列要点 → 逐条核覆盖，并写明"漏关键要点最多 4 分"；裁判还要输出它列的要点（`correctness_points`），让"列了不核"可被复查
2. 给前 20 题补 `expected_points`，要点只取金标章节支持的范围

**第二轮**——门禁通过：

| correctness | 第一轮 | 第二轮 |
|---|---|---|
| MAE | 0.55 | **0.40** |
| 相邻一致率 | 0.85 | **1.00** |
| 最大分歧 | Δ=-2 | **Δ=±1** |
| 方向性（裁判偏高/人工偏高） | 7 / 1 | 5 / 4 |

**复审 9 条分歧后的归因**（这套评测最有价值的产出）：裁判读漏或"列了不核" 3 条、**我写的要点超出金标章节支持范围 3 条**（已修）、人工主观偏严 3 条。也就是说 MAE 里约 1/3 是裁判的错、约 1/3 是尺子的错、约 1/3 是标注口径差异——**只看总分定位不了问题，必须把"方向性 + 分歧明细"做成校准报告的一等公民**。

三个设计取舍：

- **裁判要自己再取一次上下文**：`/api/chat` 的轨迹只落了来源与章节、**没落正文**（`RagChatService.buildRetrievalSnapshot` 的 `describe()`），而 faithfulness 必须看到正文，因此用同一 query 与同一 `(candidateK, rerankTopK)` 复现一次检索（检索确定性，结果与送进模型的一致）。
- **人工与裁判独立取数**：`human_rate.py` 与 `judge_eval.py` 各自调一次 `/api/chat`，刻意不让人工先看到裁判分数（锚定会让一致率失真）。
- **口径纪律同检索评测**：报告与落盘都带 `--note` 语料条件，不同语料的数字不可比、不可混用。

## 已知局限

- **裁判分数未经校准不可用**：LLM 裁判会不稳、有位置/啰嗦偏差；必须先跑 `judge_calibrate.py` 与人工评分比对一致率，未达标（相邻一致率 < 0.8 或 MAE > 0.5）就不得对外下结论
- **生成质量评测是分钟级**：每条要 2 次本地 LLM 调用，且生成/裁判用不同模型会触发 Ollama 换模型加载，远慢于检索评测，建议分批 `--limit`
- **correctness 依赖要点标尺**：目前仅前 20 题配了 `expected_points`，其余 114 条仍由裁判自主列要点评判，口径弱一档；全量跑批的结论必须注明这一差异
- **裁判会"字面匹配"式扣分**：修复偏宽之后出现反向偏差——回答已语义覆盖要点、只因没逐字提到就被扣 1 分（如第 17/19 题）。7B 裁判判"完整性"的能力有限，这是当前方案的上限
- **校准样本区分度低**：20 条人工样本是最直白的问法，分数挤在 4~5（faithfulness / relevancy 20 条完全一致，kappa 在零方差下不可读）。结论只代表"易题"，换难题需重新校准
- **尺子有"拟合人工"的风险**：`expected_points` 是对照人工分数修订的，MAE 下降有一部分来自尺子贴合人工，而非裁判能力提升
- **没有 Web 界面**：目前只有 REST 接口，需要前端或接口调试工具使用
- **强依赖本地模型**：对话与嵌入都走本机 Ollama（换模型需多处同步修改）；精排服务首次启动要从 HuggingFace 下载权重
- **语料规模小**：172 篇（27 自建 + 142 官方 + 3 测试）属验证性质，未做过百万级向量的性能测试
- **PDF 只处理文字层**：表格结构、图片、扫描件、水印都未专门处理
- **评测集自建**：134 条标注由本人编写，不等同于公开基准
- **反馈样本量决定闭环上限**：阈值重标定依赖"带期望来源的反馈"，样本不足时脚本只给参考值（`recommend_threshold` 会标记 `reliable: false`）。线上闭环要跑起来，还得先有人用、有人反馈
- **自动归因覆盖不到生成层细节**：能定位到"生成层问题"，但为什么写错（prompt 约束、上下文顺序、模型能力）仍需人工看 case
- **应用启动依赖数据库**：`qa_trace` / `qa_feedback` 表在启动时自动创建，因此必须先起 PostgreSQL（轨迹写入失败只告警不阻断问答）
- **会话记忆依赖 Redis，但只做增益**：Redis 不可用时自动降级为单轮问答（fail-open）；代价是多轮场景下反问"它"会检索不到
- **指代改写多花一次模型调用**：只在有历史对话时触发；且改写质量取决于模型，脚本只做"是否补出实体"的确定性检查，语义正确性仍需人工核对改写前后对照
- **会话记忆是进程外的**：多轮上下文存在 Redis 里（30 分钟 TTL），不落库也不跨会话共享 —— 换会话即从零开始，这是有意的隐私与成本取舍
