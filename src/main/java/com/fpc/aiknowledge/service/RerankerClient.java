
package com.fpc.aiknowledge.service;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.ai.document.Document;
import org.springframework.stereotype.Service;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

@Service
public class RerankerClient {

    private static final String RERANKER_URL =
            "http://127.0.0.1:8001/rerank";

    private final HttpClient httpClient;
    private final ObjectMapper objectMapper;

    public RerankerClient() {

        /*
         * 强制使用 HTTP/1.1。
         *
         * 当前 Reranker 是 FastAPI + Uvicorn 服务，
         * Java HttpClient 默认会尝试协商 HTTP/2。
         * 这里显式指定 HTTP/1.1，避免客户端与 Uvicorn
         * 在本地服务通信时出现请求体传输兼容问题。
         */
        this.httpClient = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_1_1)
                .connectTimeout(Duration.ofSeconds(10))
                .build();

        this.objectMapper = new ObjectMapper();
    }

    public List<Document> rerank(
            String query,
            List<Document> documents,
            int topK) throws Exception {

        if (documents == null || documents.isEmpty()) {
            return List.of();
        }

        /*
         * 保存原始 Document。
         *
         * Reranker 返回结果后，根据 id 找回原始 Document，
         * 从而保留原始 metadata。
         */
        Map<String, Document> originalDocuments =
                new HashMap<>();

        List<RerankDocument> requestDocuments =
                new ArrayList<>();

        for (int i = 0; i < documents.size(); i++) {

            Document document = documents.get(i);

            String id = document.getId();

            /*
             * 如果 Spring AI Document 没有可用 id，
             * 使用 document_id + chunk_index 构造稳定 id。
             */
            if (id == null || id.isBlank()) {

                Object documentId =
                        document.getMetadata()
                                .get("document_id");

                Object chunkIndex =
                        document.getMetadata()
                                .get("chunk_index");

                if (documentId != null
                        && chunkIndex != null) {

                    id = documentId
                            + "#"
                            + chunkIndex;

                } else {

                    id = String.valueOf(i);
                }
            }

            requestDocuments.add(
                    new RerankDocument(
                            id,
                            document.getText()
                    )
            );

            originalDocuments.put(
                    id,
                    document
            );
        }

        /*
         * 构造 Reranker 请求。
         */
        RerankRequest requestBody =
                new RerankRequest(
                        query,
                        requestDocuments,
                        topK
                );

        /*
         * 序列化 JSON。
         */
        String requestJson =
                objectMapper.writeValueAsString(
                        requestBody
                );

        /*
         * 调试日志：
         * 查看 Java 实际发送的 JSON。
         */
        System.out.println(
                "========== Reranker Request JSON =========="
        );

        System.out.println(requestJson);

        System.out.println(
                "==========================================="
        );

        /*
         * 使用 UTF-8 字节发送请求体。
         *
         * 相比 ofString，这里显式指定 UTF-8，
         * 确保中文 query/content 按 UTF-8 编码发送。
         */
        HttpRequest request =
                HttpRequest.newBuilder()
                        .uri(URI.create(RERANKER_URL))
                        .timeout(Duration.ofSeconds(120))
                        .header(
                                "Content-Type",
                                "application/json; charset=UTF-8"
                        )
                        .header(
                                "Accept",
                                "application/json"
                        )
                        .POST(
                                HttpRequest.BodyPublishers
                                        .ofByteArray(
                                                requestJson.getBytes(
                                                        StandardCharsets.UTF_8
                                                )
                                        )
                        )
                        .build();

        /*
         * 发送 HTTP 请求。
         */
        HttpResponse<String> response =
                httpClient.send(
                        request,
                        HttpResponse.BodyHandlers
                                .ofString(
                                        StandardCharsets.UTF_8
                                )
                );

        /*
         * 调试日志：
         * 查看 Python Reranker 的 HTTP 返回。
         */
        System.out.println(
                "========== Reranker Response =========="
        );

        System.out.println(
                "HTTP Status: "
                        + response.statusCode()
        );

        System.out.println(
                response.body()
        );

        System.out.println(
                "========================================"
        );

        /*
         * Python Reranker 返回非 200 时，
         * 保留具体错误信息。
         */
        if (response.statusCode() != 200) {

            throw new IllegalStateException(
                    "Reranker service returned HTTP "
                            + response.statusCode()
                            + ": "
                            + response.body()
            );
        }

        /*
         * 解析 Python 返回的 JSON。
         */
        RerankResponse rerankResponse =
                objectMapper.readValue(
                        response.body(),
                        new TypeReference<RerankResponse>() {}
                );

        List<Document> results =
                new ArrayList<>();

        /*
         * 根据 Reranker 返回的 id，
         * 找回原始 Document。
         */
        for (RerankResult result :
                rerankResponse.results()) {

            Document original =
                    originalDocuments.get(
                            result.id()
                    );

            if (original == null) {
                continue;
            }

            /*
             * 保留原始 metadata。
             */
            Map<String, Object> metadata =
                    new HashMap<>(
                            original.getMetadata()
                    );

            /*
             * 保存 Reranker 得到的相关度分数。
             */
            metadata.put(
                    "reranker_score",
                    result.score()
            );

            /*
             * 标记当前文档经过：
             * Hybrid Retrieval + Reranker。
             */
            metadata.put(
                    "retrieval_source",
                    "hybrid_rerank"
            );

            results.add(
                    new Document(
                            original.getText(),
                            metadata
                    )
            );
        }

        return results;
    }

    /*
     * Python Reranker 请求中的单个文档。
     */
    private record RerankDocument(
            String id,
            String content
    ) {}

    /*
     * Python FastAPI 接收的请求结构：
     *
     * {
     *   "query": "...",
     *   "documents": [
     *     {
     *       "id": "...",
     *       "content": "..."
     *     }
     *   ],
     *   "top_k": 3
     * }
     */
    private record RerankRequest(
            String query,
            List<RerankDocument> documents,

            @JsonProperty("top_k")
            int topK
    ) {}

    /*
     * Python Reranker 返回的单个结果。
     */
    private record RerankResult(
            String id,
            double score,
            String content
    ) {}

    /*
     * Python Reranker 返回结构：
     *
     * {
     *   "results": [...]
     * }
     */
    private record RerankResponse(
            List<RerankResult> results
    ) {}
}
