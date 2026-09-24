package com.fpc.aiknowledge.service;

import org.springframework.ai.chat.model.ChatModel;
import org.springframework.ai.document.Document;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

@Service
public class RagChatService {

    /**
     * Reranker 相关性阈值。
     *
     * 基于当前 60 条验证集进行阈值扫描：
     * - In-KB：44 条
     * - Out-of-KB：16 条
     *
     * 当前验证集上：
     * - Threshold = 0.60
     * - Precision = 1.0000
     * - Recall = 0.9773
     * - F1 = 0.9885
     * - FAR = 0
     *
     * 因此当前实验数据集选择 0.60 作为拒答阈值。
     *
     * 注意：
     * 该阈值不是 BGE-Reranker 的通用阈值。
     * 当知识库规模或数据分布发生较大变化时，需要重新校准。
     */
    private static final double RELEVANCE_THRESHOLD = 0.60;

    private final HybridRetrievalService hybridRetrievalService;
    private final RerankerClient rerankerClient;
    private final ChatModel chatModel;

    public RagChatService(
            HybridRetrievalService hybridRetrievalService,
            RerankerClient rerankerClient,
            ChatModel chatModel) {

        this.hybridRetrievalService = hybridRetrievalService;
        this.rerankerClient = rerankerClient;
        this.chatModel = chatModel;
    }

    /**
     * RAG 主流程：
     *
     * 1. Hybrid Retrieval
     * 2. Reranker
     * 3. Relevance Threshold
     * 4. Context 构造
     * 5. LLM Generation
     * 6. 添加来源引用
     */
    public String chat(String question) throws Exception {

        // ==============================
        // 0. 参数校验
        // ==============================

        if (question == null || question.isBlank()) {
            throw new IllegalArgumentException("问题不能为空");
        }

        // ==============================
        // 1. Hybrid Retrieval
        // ==============================

        List<Document> candidates =
                hybridRetrievalService.search(question, 5);

        // ==============================
        // 2. Reranker
        // ==============================

        List<Document> documents =
                rerankerClient.rerank(
                        question,
                        candidates,
                        3
                );

        // ==============================
        // 3. 判断是否存在有效候选
        // ==============================

        if (documents.isEmpty()) {
            return "知识库中没有足够的信息，无法回答该问题。";
        }

        // ==============================
        // 4. 获取 Reranker Top-1 分数
        // ==============================

        Object scoreValue =
                documents.get(0)
                        .getMetadata()
                        .get("reranker_score");

        double topScore;

        if (scoreValue instanceof Number number) {

            topScore = number.doubleValue();

        } else {

            topScore = Double.parseDouble(
                    String.valueOf(scoreValue)
            );
        }

        // ==============================
        // 5. Relevance Threshold
        // ==============================

        if (topScore < RELEVANCE_THRESHOLD) {

            return "知识库中没有足够的信息，无法回答该问题。";
        }

        // ==============================
        // 6. 构造带编号的 Context
        // ==============================

        String context =
                buildContext(documents);

        // ==============================
        // 7. 构造来源信息
        // ==============================

        String sources =
                buildSources(documents);

        // ==============================
        // 8. 构造 Prompt
        // ==============================

        String prompt = """
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
                8. 如果知识库内容不足以回答问题，请明确说明“知识库中没有足够的信息”。
                9. 回答要简洁、准确、结构清晰。
                10. 不需要在回答末尾重复列出来源，系统会自动添加参考来源。

                ===== 知识库内容 =====

                %s

                ===== 知识库内容结束 =====

                用户问题：
                %s
                """.formatted(
                context,
                question
        );

        // ==============================
        // 9. LLM Generation
        // ==============================

        String answer =
                stripThinking(
                        chatModel.call(prompt)
                );

        // ==============================
        // 10. 返回答案 + 来源
        // ==============================

        return answer
                + "\n\n"
                + sources;
    }

    /**
     * 清理模型输出中泄漏的思考过程。
     *
     * qwen3 等思考型模型偶尔会把
     * <think>...</think> 思考内容一并输出，
     * 这里统一清理，保证最终答案干净：
     *
     * 1. 存在 </think>：丢弃其之前的全部思考内容；
     * 2. 只有 <think> 没有闭合：丢弃标记本身及之前内容。
     */
    private String stripThinking(
            String answer) {

        if (answer == null
                || answer.isBlank()) {

            return "";
        }

        String cleaned = answer;

        int endTag =
                cleaned.indexOf("</think>");

        if (endTag >= 0) {

            cleaned = cleaned.substring(
                    endTag + "</think>".length()
            );

        } else {

            int startTag =
                    cleaned.indexOf("<think>");

            if (startTag >= 0) {

                cleaned = cleaned.substring(
                        startTag + "<think>".length()
                );
            }
        }

        return cleaned.trim();
    }

    /**
     * 构造带引用编号的知识库 Context。
     *
     * 每一个最终进入 RAG 的 Document
     * 都拥有唯一的引用编号。
     *
     * Markdown 示例：
     *
     * [1] redis.md — Redis 分布式锁
     *
     * PDF 示例：
     *
     * [2] SpringBoot企业级后端开发技术手册.pdf — 第19页
     */
    private String buildContext(
            List<Document> documents) {

        StringBuilder context =
                new StringBuilder();

        for (int i = 0; i < documents.size(); i++) {

            Document document =
                    documents.get(i);

            Map<String, Object> metadata =
                    document.getMetadata();

            String source =
                    String.valueOf(
                            metadata.getOrDefault(
                                    "source",
                                    "未知来源"
                            )
                    );

            String section =
                    String.valueOf(
                            metadata.getOrDefault(
                                    "section",
                                    ""
                            )
                    );

            String pageNumber =
                    String.valueOf(
                            metadata.getOrDefault(
                                    "page_number",
                                    ""
                            )
                    );

            // ==============================
            // 引用编号
            // ==============================

            context.append("[")
                    .append(i + 1)
                    .append("] ");

            // ==============================
            // 文件名
            // ==============================

            context.append(source);

            // ==============================
            // PDF 页码
            // ==============================

            if (!pageNumber.isBlank()
                    && !"null".equals(pageNumber)) {

                context.append(" — 第")
                        .append(pageNumber)
                        .append("页");
            }

            // ==============================
            // Section
            // ==============================

            if (!section.isBlank()
                    && !"null".equals(section)) {

                context.append(" — ")
                        .append(section);
            }

            context.append("\n");

            // ==============================
            // Chunk 内容
            // ==============================

            context.append(
                    document.getText()
            );

            context.append("\n\n");
        }

        return context
                .toString()
                .trim();
    }

    /**
     * 构造最终来源列表。
     *
     * 注意：
     * 来源编号与 buildContext() 中的 Document
     * 保持严格一致。
     *
     * Markdown 示例：
     *
     * [1] redis.md — Redis 缓存击穿
     *
     * PDF 示例：
     *
     * [2] SpringBoot企业级后端开发技术手册.pdf — 第19页
     */
    private String buildSources(
            List<Document> documents) {

        if (documents == null
                || documents.isEmpty()) {

            return "参考来源：\n暂无";
        }

        List<String> lines =
                new ArrayList<>();

        for (int i = 0; i < documents.size(); i++) {

            Document document =
                    documents.get(i);

            Map<String, Object> metadata =
                    document.getMetadata();

            String source =
                    String.valueOf(
                            metadata.getOrDefault(
                                    "source",
                                    "未知来源"
                            )
                    );

            String section =
                    String.valueOf(
                            metadata.getOrDefault(
                                    "section",
                                    ""
                            )
                    );

            String pageNumber =
                    String.valueOf(
                            metadata.getOrDefault(
                                    "page_number",
                                    ""
                            )
                    );

            StringBuilder line =
                    new StringBuilder();

            // ==============================
            // 引用编号
            // ==============================

            line.append("[")
                    .append(i + 1)
                    .append("] ");

            // ==============================
            // 文件名
            // ==============================

            line.append(source);

            // ==============================
            // PDF 页码
            // ==============================

            if (!pageNumber.isBlank()
                    && !"null".equals(pageNumber)) {

                line.append(" — 第")
                        .append(pageNumber)
                        .append("页");
            }

            // ==============================
            // Section
            // ==============================

            if (!section.isBlank()
                    && !"null".equals(section)) {

                line.append(" — ")
                        .append(section);
            }

            lines.add(line.toString());
        }

        return "参考来源：\n"
                + String.join(
                        "\n",
                        lines
                );
    }
}