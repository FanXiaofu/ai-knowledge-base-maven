package com.fpc.aiknowledge.tool;

import com.fpc.aiknowledge.service.HybridRetrievalService;
import com.fpc.aiknowledge.service.RerankerClient;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.ai.document.Document;
import org.springframework.ai.tool.annotation.Tool;
import org.springframework.stereotype.Component;

import java.util.List;

@Component
public class KnowledgeSearchTool {

    private static final Logger log =
            LoggerFactory.getLogger(KnowledgeSearchTool.class);

    private final HybridRetrievalService hybridRetrievalService;
    private final RerankerClient rerankerClient;

    public KnowledgeSearchTool(
            HybridRetrievalService hybridRetrievalService,
            RerankerClient rerankerClient) {

        this.hybridRetrievalService = hybridRetrievalService;
        this.rerankerClient = rerankerClient;
    }

    @Tool(description = """
            搜索知识库中的技术文档。
            当用户询问 Java、Spring、MySQL、Redis、RabbitMQ、Docker
            或其他知识库相关的具体技术问题时使用。
            """)
    public String searchKnowledge(String query) throws Exception {

        if (query == null || query.isBlank()) {
            return "查询内容不能为空。";
        }

        long startTime = System.nanoTime();

        log.info(
                "[TOOL-CALL] tool=KnowledgeSearchTool, query={}",
                query
        );

        try {

            // 1. Hybrid Retrieval
            long retrievalStart = System.nanoTime();

            List<Document> candidates =
                    hybridRetrievalService.search(query, 3);

            long retrievalMs =
                    (System.nanoTime() - retrievalStart) / 1_000_000;

            log.info(
                    "[TOOL-RETRIEVAL] tool=KnowledgeSearchTool, candidates={}, latency_ms={}",
                    candidates.size(),
                    retrievalMs
            );

            if (candidates.isEmpty()) {

                log.info(
                        "[TOOL-RESULT] tool=KnowledgeSearchTool, result=empty"
                );

                return "知识库中没有找到相关内容。";
            }

            // 2. Reranker
            List<Document> reranked = candidates;

            long rerankStart = System.nanoTime();

            try {

                reranked =
                        rerankerClient.rerank(query, candidates, 3);

                long rerankMs =
                        (System.nanoTime() - rerankStart) / 1_000_000;

                log.info(
                        "[TOOL-RERANK] tool=KnowledgeSearchTool, results={}, latency_ms={}, status=success",
                        reranked.size(),
                        rerankMs
                );

            } catch (Exception rerankException) {

                long rerankMs =
                        (System.nanoTime() - rerankStart) / 1_000_000;

                log.warn(
                        "[TOOL-RERANK] tool=KnowledgeSearchTool, status=fallback, " +
                                "latency_ms={}, error={}",
                        rerankMs,
                        rerankException.getMessage()
                );

                log.info(
                        "[TOOL-FALLBACK] tool=KnowledgeSearchTool, " +
                                "strategy=hybrid_retrieval, results={}",
                        candidates.size()
                );

                // Reranker 不可用时：
                // 降级使用 Hybrid Retrieval 的 Top 3 结果
                reranked = candidates;
            }

            if (reranked.isEmpty()) {

                log.info(
                        "[TOOL-RESULT] tool=KnowledgeSearchTool, result=empty"
                );

                return "知识库中没有找到相关内容。";
            }

            // 3. 构造 Tool 返回结果
            StringBuilder result = new StringBuilder();

            for (int i = 0; i < reranked.size(); i++) {

                Document document = reranked.get(i);

                Object score =
                        document.getMetadata().get("reranker_score");

                Object source =
                        document.getMetadata().get("source");

                Object page =
                        document.getMetadata().get("page_number");

                Object section =
                        document.getMetadata().get("section");

                result.append("[")
                        .append(i + 1)
                        .append("]\n");

                result.append("来源：")
                        .append(source == null ? "未知" : source)
                        .append("\n");

                if (page != null) {
                    result.append("页码：")
                            .append(page)
                            .append("\n");
                }

                if (section != null) {
                    result.append("章节：")
                            .append(section)
                            .append("\n");
                }

                if (score != null) {
                    result.append("相关度：")
                            .append(score)
                            .append("\n");
                }

                result.append("内容：")
                        .append(document.getText())
                        .append("\n\n");
            }

            long totalMs =
                    (System.nanoTime() - startTime) / 1_000_000;

            log.info(
                    "[TOOL-RESULT] tool=KnowledgeSearchTool, results={}, latency_ms={}",
                    reranked.size(),
                    totalMs
            );

            return result.toString();

        } catch (Exception e) {

            long totalMs =
                    (System.nanoTime() - startTime) / 1_000_000;

            log.error(
                    "[TOOL-ERROR] tool=KnowledgeSearchTool, latency_ms={}, error={}",
                    totalMs,
                    e.getMessage(),
                    e
            );

            throw e;
        }
    }
}