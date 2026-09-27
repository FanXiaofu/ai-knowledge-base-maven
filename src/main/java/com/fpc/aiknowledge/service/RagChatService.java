package com.fpc.aiknowledge.service;

import org.springframework.ai.chat.model.ChatModel;
import org.springframework.ai.document.Document;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * RAG 主流程：会话记忆 → 查询改写 → 混合检索 → 精排 → 拒答判定 → 生成 → 附带来源。
 *
 * <p>三处与早期版本的不同：
 * <ul>
 *   <li>检索参数（阈值 / 候选数 / 精排数）来自 {@link RetrievalPolicyService}，
 *       即评测集扫参选出的策略文件，而不是写死在代码里的常量；</li>
 *   <li>每次问答落一条轨迹（{@link EvolutionStore}）：问题、召回候选、精排结果与分数、
 *       是否拒答及原因、最终回答。轨迹是 badcase 归因与评测集生长的原料；</li>
 *   <li>带 sessionId 时启用会话记忆（{@link ConversationMemoryService}）：
 *       追问先经 {@link QueryRewriteService} 做指代消解再检索，问答结束后回写窗口。
 *       不传 sessionId 就退化为单轮无状态问答，与引入记忆前完全一致。</li>
 * </ul>
 *
 * <p>拒答阈值的历史标定口径（60 条子集：44 库内 + 16 库外，阈值 0.60 时 P=1.0、FAR=0）
 * 记录在 {@link RetrievalPolicyService#DEFAULT_THRESHOLD}；
 * 阈值与语料分布绑定，换语料要用 evolution/auto_tune.py 重新标定并写入策略文件。
 */
@Service
public class RagChatService {

    private static final String REFUSE_MESSAGE =
            "知识库中没有足够的信息，无法回答该问题。";

    private static final DateTimeFormatter TRACE_TIME =
            DateTimeFormatter.ofPattern("yyyyMMdd-HHmmss");

    private final HybridRetrievalService hybridRetrievalService;
    private final RerankerClient rerankerClient;
    private final RetrievalPolicyService policyService;
    private final EvolutionStore evolutionStore;
    private final ConversationMemoryService conversationMemory;
    private final QueryRewriteService queryRewriteService;
    private final ChatModel chatModel;

    public RagChatService(
            HybridRetrievalService hybridRetrievalService,
            RerankerClient rerankerClient,
            RetrievalPolicyService policyService,
            EvolutionStore evolutionStore,
            ConversationMemoryService conversationMemory,
            QueryRewriteService queryRewriteService,
            ChatModel chatModel) {

        this.hybridRetrievalService = hybridRetrievalService;
        this.rerankerClient = rerankerClient;
        this.policyService = policyService;
        this.evolutionStore = evolutionStore;
        this.conversationMemory = conversationMemory;
        this.queryRewriteService = queryRewriteService;
        this.chatModel = chatModel;
    }

    /**
     * 一次 RAG 问答的结果。
     *
     * @param question       原始问题
     * @param answer         回答正文（含"参考来源"）
     * @param refused        是否拒答
     * @param traceId        轨迹 ID，反馈时回传（POST /api/feedback）
     * @param top1Score      精排 Top-1 分数（无候选时为 null）
     * @param threshold      本次使用的拒答阈值
     * @param sessionId      会话 ID（未传则为空）
     * @param retrievalQuery 实际用于检索的问题（会话记忆生效时是被改写过的）
     * @param rewritten      本次是否发生了查询改写
     */
    public record RagAnswer(
            String question,
            String answer,
            boolean refused,
            String traceId,
            Double top1Score,
            double threshold,
            String sessionId,
            String retrievalQuery,
            boolean rewritten) {

        public Map<String, Object> toMap() {
            Map<String, Object> map = new LinkedHashMap<>();
            map.put("question", question);
            map.put("answer", answer);
            map.put("refused", refused);
            map.put("trace_id", traceId);
            map.put("top1_score", top1Score);
            map.put("threshold", threshold);
            map.put("session_id", sessionId);
            map.put("retrieval_query", retrievalQuery);
            map.put("rewritten", rewritten);
            return map;
        }
    }

    /**
     * RAG 主流程（带会话记忆）。
     *
     * 1. 会话记忆：取出该会话最近几轮问答
     * 2. 查询改写：把"它/这个"这类指代补全成可独立检索的问题（无历史则跳过）
     * 3. Hybrid Retrieval（候选数来自策略，用改写后的问题检索）
     * 4. Reranker（精排数来自策略）
     * 5. Relevance Threshold（阈值来自策略）
     * 6. Context 构造 + LLM Generation + 来源引用
     * 7. 轨迹落库（含拒答路径与改写事实）+ 回写会话记忆
     *
     * @param sessionId 会话 ID；为空则退化为单轮无状态问答（与引入记忆前一致）
     */
    public RagAnswer chat(String question, String sessionId) throws Exception {

        if (question == null || question.isBlank()) {
            throw new IllegalArgumentException("问题不能为空");
        }

        RetrievalPolicyService.Policy policy = policyService.current();
        String traceId = newTraceId();

        // ==============================
        // 1. 会话记忆 + 2. 查询改写
        // ==============================

        ConversationMemoryService.Window window = conversationMemory.load(sessionId);
        QueryRewriteService.Rewrite rewrite = queryRewriteService.rewrite(question, window);
        String retrievalQuery = rewrite.query();

        // ==============================
        // 3. Hybrid Retrieval
        // ==============================

        List<Document> candidates =
                hybridRetrievalService.search(retrievalQuery, policy.topK());

        // ==============================
        // 4. Reranker
        // ==============================

        List<Document> documents =
                rerankerClient.rerank(retrievalQuery, candidates, policy.rerankTopK());

        Map<String, Object> retrieval =
                buildRetrievalSnapshot(candidates, documents, sessionId, window, rewrite);

        // ==============================
        // 3. 无候选：直接拒答
        // ==============================

        if (documents.isEmpty()) {
            return refuse(
                    traceId,
                    question,
                    sessionId,
                    rewrite,
                    "no_candidate",
                    null,
                    policy,
                    retrieval
            );
        }

        // ==============================
        // 4. 精排 Top-1 分数
        // ==============================

        double topScore = readRerankerScore(documents.get(0));

        // ==============================
        // 5. 阈值判定
        // ==============================

        if (topScore < policy.relevanceThreshold()) {
            return refuse(
                    traceId,
                    question,
                    sessionId,
                    rewrite,
                    "below_threshold",
                    topScore,
                    policy,
                    retrieval
            );
        }

        // ==============================
        // 6. Context 与来源
        // ==============================

        String context = buildContext(documents);
        String sources = buildSources(documents);
        String prompt = buildPrompt(context, question);

        // ==============================
        // 7. LLM Generation
        // ==============================

        String answer = stripThinking(chatModel.call(prompt));
        String fullAnswer = answer + "\n\n" + sources;

        // ==============================
        // 8. 轨迹落库 + 会话记忆回写
        // ==============================

        evolutionStore.recordTrace(
                traceId,
                question,
                false,
                null,
                topScore,
                policy.relevanceThreshold(),
                policy.method(),
                retrieval,
                fullAnswer
        );

        rememberTurn(sessionId, question, fullAnswer, documents);

        return new RagAnswer(
                question,
                fullAnswer,
                false,
                traceId,
                topScore,
                policy.relevanceThreshold(),
                sessionId,
                retrievalQuery,
                rewrite.rewritten()
        );
    }

    private RagAnswer refuse(
            String traceId,
            String question,
            String sessionId,
            QueryRewriteService.Rewrite rewrite,
            String reason,
            Double topScore,
            RetrievalPolicyService.Policy policy,
            Map<String, Object> retrieval) {

        evolutionStore.recordTrace(
                traceId,
                question,
                true,
                reason,
                topScore,
                policy.relevanceThreshold(),
                policy.method(),
                retrieval,
                REFUSE_MESSAGE
        );

        // 拒答同样记进会话：下一轮的指代可能正是指向这个（没答上来的）话题
        rememberTurn(sessionId, question, REFUSE_MESSAGE, List.of());

        return new RagAnswer(
                question,
                REFUSE_MESSAGE,
                true,
                traceId,
                topScore,
                policy.relevanceThreshold(),
                sessionId,
                rewrite.query(),
                rewrite.rewritten()
        );
    }

    /**
     * 回写会话记忆：助手侧只存回答摘要（去掉参考来源后的前 200 字）与命中的来源名，
     * 避免把整篇回答塞回下一轮的改写提示词。
     */
    private void rememberTurn(String sessionId, String question, String answer, List<Document> documents) {

        if (sessionId == null || sessionId.isBlank()) {
            return;
        }

        String body = answer == null ? "" : answer.split("参考来源")[0].strip();
        if (body.length() > 200) {
            body = body.substring(0, 200) + "…";
        }

        List<String> sources = new ArrayList<>();
        for (Document document : documents) {
            Object source = document.getMetadata().get("source");
            if (source != null) {
                sources.add(String.valueOf(source));
            }
        }

        conversationMemory.append(
                sessionId,
                ConversationMemoryService.Turn.of(question, body, sources)
        );
    }

    private String newTraceId() {
        return "qa-"
                + LocalDateTime.now().format(TRACE_TIME)
                + "-"
                + UUID.randomUUID().toString().substring(0, 6);
    }

    private double readRerankerScore(Document document) {

        Object scoreValue =
                document.getMetadata().get("reranker_score");

        if (scoreValue instanceof Number number) {
            return number.doubleValue();
        }

        return Double.parseDouble(String.valueOf(scoreValue));
    }

    /**
     * 记录检索现场：召回候选（精排前）与精排结果分开存，另附会话与改写信息。
     *
     * 归因时用得上：金标出现在候选里却不在精排结果里 → 排序/阈值问题；
     * 候选中就没有 → 召回问题。只存最终片段的话这两种情况分不开。
     * 改写信息（原始问题 vs 实际检索问题）用于评估会话记忆的收益：
     * 没有它就无法判断"检索失败"是改写没生效还是改写改错了。
     */
    private Map<String, Object> buildRetrievalSnapshot(
            List<Document> candidates,
            List<Document> reranked,
            String sessionId,
            ConversationMemoryService.Window window,
            QueryRewriteService.Rewrite rewrite) {

        Map<String, Object> snapshot = new LinkedHashMap<>();

        snapshot.put("candidates", describe(candidates, false));
        snapshot.put("reranked", describe(reranked, true));

        RetrievalPolicyService.Policy policy = policyService.current();
        snapshot.put("top_k", policy.topK());
        snapshot.put("rerank_top_k", policy.rerankTopK());

        snapshot.put("session_id", sessionId);
        snapshot.put("memory_turns", window == null ? 0 : window.size());
        snapshot.put("retrieval_query", rewrite.query());
        snapshot.put("rewritten", rewrite.rewritten());
        snapshot.put("rewrite_reason", rewrite.reason());

        return snapshot;
    }

    private List<Map<String, Object>> describe(
            List<Document> documents,
            boolean withScore) {

        List<Map<String, Object>> rows = new ArrayList<>();

        if (documents == null) {
            return rows;
        }

        for (int i = 0; i < documents.size(); i++) {

            Map<String, Object> metadata = documents.get(i).getMetadata();
            Map<String, Object> row = new LinkedHashMap<>();

            row.put("rank", i + 1);
            row.put("source", metadata.get("source"));
            row.put("section", metadata.get("section"));
            row.put("page_number", metadata.get("page_number"));
            row.put("document_id", metadata.get("document_id"));

            if (withScore && metadata.get("reranker_score") != null) {
                row.put("reranker_score", metadata.get("reranker_score"));
            }

            rows.add(row);
        }

        return rows;
    }

    private String buildPrompt(String context, String question) {

        return """
                你是一个企业内部知识库问答助手。

                请严格根据下面提供的知识库内容回答用户问题。

                要求：
                1. 只能使用知识库中的信息回答问题。
                2. 不要编造知识库中不存在的内容。
                3. 如果多个知识片段共同支持一个结论，可以同时引用多个来源。
                4. 使用知识库内容进行回答时，必须在对应句子末尾添加引用编号。
                5. 引用格式必须使用 [1]、[2]、[3] 等形式。
                6. 引用编号必须来自实际提供的知识片段。
                7. 不要生成不存在的引用编号。
                8. 如果知识库内容不足以回答问题，请明确说明"知识库中没有足够的信息"。
                9. 回答要简洁、准确、结构清晰。
                10. 不需要在回答末尾重复列出来源，系统会自动添加参考来源。

                ===== 知识库内容 =====

                %s

                ===== 知识库内容结束 =====

                用户问题：
                %s
                """.formatted(context, question);
    }

    /**
     * 清理模型输出中泄漏的思考过程（qwen3 等思考型模型偶发）。
     */
    private String stripThinking(String answer) {

        if (answer == null || answer.isBlank()) {
            return "";
        }

        String cleaned = answer;

        int endTag = cleaned.indexOf("</think>");

        if (endTag >= 0) {

            cleaned = cleaned.substring(endTag + "</think>".length());

        } else {

            int startTag = cleaned.indexOf("<think>");

            if (startTag >= 0) {
                cleaned = cleaned.substring(startTag + "<think>".length());
            }
        }

        return cleaned.trim();
    }

    /**
     * 构造带引用编号的知识库 Context。
     *
     * [1] redis.md — Redis 分布式锁
     * [2] SpringBoot企业级后端开发技术手册.pdf — 第19页
     */
    private String buildContext(List<Document> documents) {

        StringBuilder context = new StringBuilder();

        for (int i = 0; i < documents.size(); i++) {

            Document document = documents.get(i);
            Map<String, Object> metadata = document.getMetadata();

            String source = String.valueOf(
                    metadata.getOrDefault("source", "未知来源"));

            String section = String.valueOf(
                    metadata.getOrDefault("section", ""));

            String pageNumber = String.valueOf(
                    metadata.getOrDefault("page_number", ""));

            context.append("[").append(i + 1).append("] ").append(source);

            if (!pageNumber.isBlank() && !"null".equals(pageNumber)) {
                context.append(" — 第").append(pageNumber).append("页");
            }

            if (!section.isBlank() && !"null".equals(section)) {
                context.append(" — ").append(section);
            }

            context.append("\n");
            context.append(document.getText());
            context.append("\n\n");
        }

        return context.toString().trim();
    }

    /**
     * 构造最终来源列表，编号与 buildContext() 严格一致。
     */
    private String buildSources(List<Document> documents) {

        if (documents == null || documents.isEmpty()) {
            return "参考来源：\n暂无";
        }

        List<String> lines = new ArrayList<>();

        for (int i = 0; i < documents.size(); i++) {

            Map<String, Object> metadata = documents.get(i).getMetadata();

            String source = String.valueOf(
                    metadata.getOrDefault("source", "未知来源"));

            String section = String.valueOf(
                    metadata.getOrDefault("section", ""));

            String pageNumber = String.valueOf(
                    metadata.getOrDefault("page_number", ""));

            StringBuilder line = new StringBuilder();
            line.append("[").append(i + 1).append("] ").append(source);

            if (!pageNumber.isBlank() && !"null".equals(pageNumber)) {
                line.append(" — 第").append(pageNumber).append("页");
            }

            if (!section.isBlank() && !"null".equals(section)) {
                line.append(" — ").append(section);
            }

            lines.add(line.toString());
        }

        return "参考来源：\n" + String.join("\n", lines);
    }
}
