package com.fpc.aiknowledge.controller;

import com.fpc.aiknowledge.service.Bm25Service;
import com.fpc.aiknowledge.service.HybridRetrievalService;
import com.fpc.aiknowledge.service.QueryExpansionService;
import com.fpc.aiknowledge.service.RerankerClient;
import com.fpc.aiknowledge.service.RetrievalService;
import org.springframework.ai.document.Document;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/api/knowledge")
public class KnowledgeSearchController {

    private final RetrievalService retrievalService;
    private final Bm25Service bm25Service;
    private final HybridRetrievalService hybridRetrievalService;
    private final RerankerClient rerankerClient;
    private final QueryExpansionService queryExpansionService;

    public KnowledgeSearchController(
            RetrievalService retrievalService,
            Bm25Service bm25Service,
            HybridRetrievalService hybridRetrievalService,
            RerankerClient rerankerClient,
            QueryExpansionService queryExpansionService) {

        this.retrievalService = retrievalService;
        this.bm25Service = bm25Service;
        this.hybridRetrievalService = hybridRetrievalService;
        this.rerankerClient = rerankerClient;
        this.queryExpansionService = queryExpansionService;
    }

    @GetMapping("/search")
    public List<Document> search(
            @RequestParam String query,
            @RequestParam(defaultValue = "3") int topK) {

        return retrievalService.search(query, topK);
    }

    @GetMapping("/bm25-search")
    public List<Document> bm25Search(
            @RequestParam String query,
            @RequestParam(defaultValue = "3") int topK) {

        return bm25Service.search(query, topK);
    }

    @GetMapping("/hybrid-search")
    public List<Document> hybridSearch(
            @RequestParam String query,
            @RequestParam(defaultValue = "3") int topK) {

        return hybridRetrievalService.search(
                query,
                topK
        );
    }

    @GetMapping("/expand-query")
    public List<String> expandQuery(
            @RequestParam String query) {

        return queryExpansionService.expand(query);
    }

    /**
     * Query Expansion + Vector + BM25 + Global RRF。
     */
    @GetMapping("/hybrid-expansion-search")
    public List<Document> hybridExpansionSearch(
            @RequestParam String query,
            @RequestParam(defaultValue = "8") int topK) {

        return hybridRetrievalService
                .searchWithExpansion(
                        query,
                        topK
                );
    }

    /**
     * 原始 Hybrid + Reranker。
     */
    @GetMapping("/rerank-test")
    public List<Document> rerankTest(
            @RequestParam String query)
            throws Exception {

        List<Document> candidates =
                hybridRetrievalService.search(
                        query,
                        5
                );

        return rerankerClient.rerank(
                query,
                candidates,
                3
        );
    }

    /**
     * Query Expansion + Global RRF + Reranker。
     *
     * 流程：
     *
     * 原始 Query
     *       ↓
     * Query Expansion
     *       ↓
     * Vector + BM25
     *       ↓
     * Global RRF Top 8
     *       ↓
     * Reranker
     *       ↓
     * Top 3
     *
     * 注意：
     * Reranker 始终使用用户的原始 Query。
     */
    @GetMapping("/expansion-rerank-test")
    public List<Document> expansionRerankTest(
            @RequestParam String query)
            throws Exception {

        /*
         * Query Expansion + Global RRF
         *
         * Top 8 作为 Reranker 候选集。
         */
        List<Document> candidates =
                hybridRetrievalService
                        .searchWithExpansion(
                                query,
                                8
                        );

        /*
         * 使用原始用户 Query
         * 对 Global RRF Top 8 进行重新排序。
         */
        return rerankerClient.rerank(
                query,
                candidates,
                3
        );
    }

        /**
         * Hybrid Retrieval 参数实验。
         *
         * 用于测试不同 Vector / BM25 候选集大小
         * 以及不同 RRF K 对最终检索结果的影响。
         *
         * 流程：
         *
         * Vector Top vectorK
         *          +
         * BM25 Top bm25K
         *          ↓
         *        RRF
         *          ↓
         *      Final TopK
         */
        @GetMapping("/hybrid-experiment")
        public List<Document> hybridExperiment(
                @RequestParam String query,
                @RequestParam(defaultValue = "5") int topK,
                @RequestParam(defaultValue = "5") int vectorK,
                @RequestParam(defaultValue = "5") int bm25K,
                @RequestParam(defaultValue = "60") int rrfK) {

        return hybridRetrievalService.search(
                query,
                topK,
                vectorK,
                bm25K,
                rrfK
        );
    }
}