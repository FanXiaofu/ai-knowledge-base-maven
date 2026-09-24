
package com.fpc.aiknowledge.service;

import org.springframework.ai.document.Document;
import org.springframework.ai.vectorstore.SearchRequest;
import org.springframework.ai.vectorstore.VectorStore;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

@Service
public class HybridRetrievalService {

    /**
     * 默认 RRF 常数。
     */
    private static final int DEFAULT_RRF_K = 60;

    private final VectorStore vectorStore;
    private final Bm25Service bm25Service;
    private final QueryExpansionService queryExpansionService;

    public HybridRetrievalService(
            VectorStore vectorStore,
            Bm25Service bm25Service,
            QueryExpansionService queryExpansionService) {

        this.vectorStore = vectorStore;
        this.bm25Service = bm25Service;
        this.queryExpansionService = queryExpansionService;
    }

    /**
     * 原始 Hybrid Retrieval。
     *
     * 使用默认候选集：
     *
     * Vector Candidate = max(topK * 2, 5)
     * BM25 Candidate   = max(topK * 2, 5)
     * RRF K            = 60
     *
     * Vector + BM25 → RRF
     */
    public List<Document> search(String query, int topK) {

        int candidateK = Math.max(topK * 2, 5);

        return search(
                query,
                topK,
                candidateK,
                candidateK,
                DEFAULT_RRF_K
        );
    }

    /**
     * 参数化 Hybrid Retrieval。
     *
     * 用于 RRF 参数实验。
     *
     * @param query      用户查询
     * @param topK       最终返回数量
     * @param vectorK    Vector Retrieval 候选数量
     * @param bm25K      BM25 Retrieval 候选数量
     * @param rrfK       RRF 常数
     */
    public List<Document> search(
            String query,
            int topK,
            int vectorK,
            int bm25K,
            int rrfK) {

        /*
         * ==========================
         * Vector Retrieval
         * ==========================
         */
        SearchRequest vectorRequest =
                SearchRequest.builder()
                        .query(query)
                        .topK(vectorK)
                        .build();

        List<Document> vectorDocuments =
                vectorStore.similaritySearch(vectorRequest);

        /*
         * ==========================
         * BM25 Retrieval
         * ==========================
         */
        List<Document> bm25Documents =
                bm25Service.search(query, bm25K);

        /*
         * ==========================
         * RRF Fusion
         * ==========================
         */
        Map<String, RrfDocument> fusionMap =
                new HashMap<>();

        // Vector Retrieval
        for (int i = 0;
             i < vectorDocuments.size();
             i++) {

            Document document =
                    vectorDocuments.get(i);

            String key =
                    buildDocumentKey(document);

            int rank = i + 1;

            RrfDocument rrfDocument =
                    fusionMap.computeIfAbsent(
                            key,
                            k -> new RrfDocument(document)
                    );

            rrfDocument.vectorRank = rank;

            rrfDocument.rrfScore +=
                    1.0 / (rrfK + rank);
        }

        // BM25 Retrieval
        for (int i = 0;
             i < bm25Documents.size();
             i++) {

            Document document =
                    bm25Documents.get(i);

            String key =
                    buildDocumentKey(document);

            int rank = i + 1;

            RrfDocument rrfDocument =
                    fusionMap.computeIfAbsent(
                            key,
                            k -> new RrfDocument(document)
                    );

            rrfDocument.bm25Rank = rank;

            rrfDocument.rrfScore +=
                    1.0 / (rrfK + rank);
        }

        /*
         * ==========================
         * Global RRF Ranking
         * ==========================
         */
        List<RrfDocument> rankedDocuments =
                new ArrayList<>(fusionMap.values());

        rankedDocuments.sort(
                Comparator.comparingDouble(
                        RrfDocument::getRrfScore
                ).reversed()
        );

        /*
         * ==========================
         * Top K
         * ==========================
         */
        return rankedDocuments.stream()
                .limit(topK)
                .map(this::toDocument)
                .toList();
    }

    /**
     * Query Expansion + Global RRF。
     *
     * 当前实验阶段暂时保持原逻辑。
     */
    public List<Document> searchWithExpansion(
            String originalQuery,
            int topK) {

        List<String> queries =
                queryExpansionService.expand(originalQuery);

        /*
         * 防止 Query Expansion 异常时没有任何查询。
         */
        if (queries == null || queries.isEmpty()) {
            queries = List.of(originalQuery);
        }

        Map<String, RrfDocument> fusionMap =
                new HashMap<>();

        /*
         * 对原始 Query + Expansion Queries
         * 分别执行 Vector + BM25。
         */
        for (String query : queries) {

            if (query == null || query.isBlank()) {
                continue;
            }

            int candidateK =
                    Math.max(topK * 2, 5);

            /*
             * ==========================
             * Vector Retrieval
             * ==========================
             */
            SearchRequest vectorRequest =
                    SearchRequest.builder()
                            .query(query)
                            .topK(candidateK)
                            .build();

            List<Document> vectorDocuments =
                    vectorStore.similaritySearch(
                            vectorRequest
                    );

            for (int i = 0;
                 i < vectorDocuments.size();
                 i++) {

                Document document =
                        vectorDocuments.get(i);

                String key =
                        buildDocumentKey(document);

                int rank = i + 1;

                RrfDocument rrfDocument =
                        fusionMap.computeIfAbsent(
                                key,
                                k -> new RrfDocument(document)
                        );

                /*
                 * Expansion Query 的 Rank
                 * 是局部 Rank，因此不记录。
                 */
                rrfDocument.rrfScore +=
                        1.0 / (DEFAULT_RRF_K + rank);
            }

            /*
             * ==========================
             * BM25 Retrieval
             * ==========================
             */
            List<Document> bm25Documents =
                    bm25Service.search(
                            query,
                            candidateK
                    );

            for (int i = 0;
                 i < bm25Documents.size();
                 i++) {

                Document document =
                        bm25Documents.get(i);

                String key =
                        buildDocumentKey(document);

                int rank = i + 1;

                RrfDocument rrfDocument =
                        fusionMap.computeIfAbsent(
                                key,
                                k -> new RrfDocument(document)
                        );

                rrfDocument.rrfScore +=
                        1.0 / (DEFAULT_RRF_K + rank);
            }
        }

        /*
         * Global RRF 排序。
         */
        List<RrfDocument> rankedDocuments =
                new ArrayList<>(fusionMap.values());

        rankedDocuments.sort(
                Comparator.comparingDouble(
                        RrfDocument::getRrfScore
                ).reversed()
        );

        /*
         * 返回 Global RRF Top K。
         */
        return rankedDocuments.stream()
                .limit(topK)
                .map(this::toExpandedDocument)
                .toList();
    }

    /**
     * 根据 document_id + chunk_index
     * 唯一确定一个知识库 Chunk。
     */
    private String buildDocumentKey(
            Document document) {

        Map<String, Object> metadata =
                document.getMetadata();

        Object documentId =
                metadata.get("document_id");

        Object chunkIndex =
                metadata.get("chunk_index");

        if (documentId != null
                && chunkIndex != null) {

            return documentId
                    + "#"
                    + chunkIndex;
        }

        Object source =
                metadata.get("source");

        if (source != null
                && chunkIndex != null) {

            return source
                    + "#"
                    + chunkIndex;
        }

        return document.getId();
    }

    /**
     * 原始 Hybrid Retrieval 的结果转换。
     */
    private Document toDocument(
            RrfDocument rrfDocument) {

        Document original =
                rrfDocument.document;

        Map<String, Object> metadata =
                new HashMap<>(
                        original.getMetadata()
                );

        metadata.put(
                "retrieval_source",
                "hybrid"
        );

        metadata.put(
                "rrf_score",
                rrfDocument.rrfScore
        );

        if (rrfDocument.vectorRank != null) {

            metadata.put(
                    "vector_rank",
                    rrfDocument.vectorRank
            );
        }

        if (rrfDocument.bm25Rank != null) {

            metadata.put(
                    "bm25_rank",
                    rrfDocument.bm25Rank
            );
        }

        return new Document(
                original.getText(),
                metadata
        );
    }

    /**
     * Query Expansion + Global RRF 的结果转换。
     */
    private Document toExpandedDocument(
            RrfDocument rrfDocument) {

        Document original =
                rrfDocument.document;

        Map<String, Object> metadata =
                new HashMap<>(
                        original.getMetadata()
                );

        metadata.put(
                "retrieval_source",
                "hybrid_expansion"
        );

        metadata.put(
                "rrf_score",
                rrfDocument.rrfScore
        );

        return new Document(
                original.getText(),
                metadata
        );
    }

    /**
     * RRF 中间结果。
     */
    private static class RrfDocument {

        private final Document document;

        private double rrfScore = 0.0;

        /*
         * 只有普通 Hybrid Retrieval 使用。
         */
        private Integer vectorRank;

        private Integer bm25Rank;

        public RrfDocument(Document document) {
            this.document = document;
        }

        public double getRrfScore() {
            return rrfScore;
        }
    }
}

