package com.fpc.aiknowledge.service;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.ai.document.Document;
import org.springframework.stereotype.Service;

import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.util.*;

/**
 * BM25 检索。
 *
 * 实现要点：
 *
 * 1. 内存倒排索引。
 *    早期实现是"每次查询都把整张表读出来重新分词打分"，
 *    在 236 个 chunk 时约 50ms，扩充到 1200+ 个 chunk 后
 *    涨到 400ms 以上，且该开销会随语料线性增长。
 *    现在改为构建一次倒排索引（词项 → 文档及词频），
 *    查询时只对命中的文档打分，与语料总量基本解耦。
 *
 * 2. 索引失效由导入流程触发。
 *    KnowledgeIngestionService 在删除/写入向量库后
 *    调用 invalidate()，下次查询时惰性重建。
 *
 * 3. 并发模型。
 *    索引快照不可变，用 volatile 引用发布；
 *    读取完全无锁，重建过程加锁且不阻塞读取方。
 */
@Service
public class Bm25Service {

    private static final double K1 = 1.5;
    private static final double B = 0.75;

    private final DataSource dataSource;
    private final ObjectMapper objectMapper;

    /**
     * 当前索引快照。为 null 表示需要（重新）构建。
     */
    private volatile Bm25Index index;

    private final Object buildLock = new Object();

    public Bm25Service(DataSource dataSource) {
        this.dataSource = dataSource;
        this.objectMapper = new ObjectMapper();
    }

    /**
     * 使索引失效，下次查询时重建。
     * 知识库发生任何变更后都应调用。
     */
    public void invalidate() {
        index = null;
    }

    /**
     * 当前索引中的文档数量（未构建时返回 -1）。
     */
    public int getIndexedDocumentCount() {
        Bm25Index current = index;
        return current == null ? -1 : current.documents.size();
    }

    /**
     * BM25 检索
     */
    public List<Document> search(String query, int topK) {

        Bm25Index current = getIndex();

        if (current.documents.isEmpty()) {
            return Collections.emptyList();
        }

        List<String> queryTokens = tokenize(query);

        if (queryTokens.isEmpty()) {
            return Collections.emptyList();
        }

        /*
         * 同一查询里重复出现的词只计一次，
         * 避免人为放大某个词的权重。
         */
        Set<String> uniqueTokens =
                new LinkedHashSet<>(queryTokens);

        /*
         * 倒排索引打分：
         * 只遍历包含查询词的文档，而不是全部文档。
         */
        Map<Integer, Double> scores =
                new HashMap<>();

        for (String token : uniqueTokens) {

            List<Posting> postings =
                    current.postings.get(token);

            if (postings == null) {
                continue;
            }

            int documentFrequency = postings.size();

            double idf = Math.log(
                    1.0
                            + (current.documentCount
                            - documentFrequency
                            + 0.5)
                            / (documentFrequency + 0.5)
            );

            for (Posting posting : postings) {

                IndexedDocument document =
                        current.documents.get(
                                posting.documentIndex()
                        );

                double numerator =
                        posting.termFrequency() * (K1 + 1);

                double denominator =
                        posting.termFrequency()
                                + K1 * (
                                1 - B
                                        + B
                                        * document.length()
                                        / current.avgDocLength
                        );

                scores.merge(
                        posting.documentIndex(),
                        idf * numerator / denominator,
                        Double::sum
                );
            }
        }

        return scores.entrySet().stream()
                .sorted(
                        Map.Entry
                                .<Integer, Double>comparingByValue()
                                .reversed()
                )
                .limit(topK)
                .map(entry -> toSpringDocument(
                        current.documents.get(
                                entry.getKey()
                        ),
                        entry.getValue()
                ))
                .toList();
    }

    /**
     * 获取索引，必要时惰性构建。
     */
    private Bm25Index getIndex() {

        Bm25Index current = index;

        if (current != null) {
            return current;
        }

        synchronized (buildLock) {

            /*
             * 双重检查：可能在等锁期间已由其他线程重建。
             */
            if (index != null) {
                return index;
            }

            long start = System.nanoTime();

            Bm25Index built = buildIndex();

            long elapsedMs =
                    (System.nanoTime() - start) / 1_000_000;

            System.out.println(
                    "BM25 倒排索引构建完成：文档 "
                            + built.documents.size()
                            + " 篇，词项 "
                            + built.postings.size()
                            + " 个，耗时 "
                            + elapsedMs
                            + " ms"
            );

            index = built;

            return built;
        }
    }

    /**
     * 构建倒排索引快照。
     */
    private Bm25Index buildIndex() {

        List<IndexedDocument> documents =
                new ArrayList<>();

        Map<String, List<Posting>> postings =
                new HashMap<>();

        long totalLength = 0;

        for (Bm25Row row : loadRows()) {

            List<String> tokens = tokenize(row.content());

            Map<String, Integer> termFrequency =
                    new HashMap<>();

            for (String token : tokens) {
                termFrequency.merge(token, 1, Integer::sum);
            }

            int documentIndex = documents.size();

            IndexedDocument document = new IndexedDocument(
                    row.id(),
                    row.content(),
                    row.documentId(),
                    row.chunkIndex(),
                    row.source(),
                    row.section(),
                    row.filePath(),
                    row.documentType(),
                    row.totalChunks(),
                    tokens.size()
            );

            documents.add(document);

            totalLength += tokens.size();

            for (Map.Entry<String, Integer> entry
                    : termFrequency.entrySet()) {

                postings
                        .computeIfAbsent(
                                entry.getKey(),
                                k -> new ArrayList<>()
                        )
                        .add(
                                new Posting(
                                        documentIndex,
                                        entry.getValue()
                                )
                        );
            }
        }

        double avgDocLength = documents.isEmpty()
                ? 0.0
                : (double) totalLength / documents.size();

        return new Bm25Index(
                List.copyOf(documents),
                Map.copyOf(postings),
                avgDocLength,
                documents.size()
        );
    }

    /**
     * 从 PostgreSQL 读取当前知识库中的所有 Chunk。
     * 仅在重建索引时调用。
     */
    private List<Bm25Row> loadRows() {

        String sql = """
                SELECT id, content, metadata
                FROM vector_store
                WHERE content IS NOT NULL
                """;

        List<Bm25Row> rows = new ArrayList<>();

        try (
                Connection connection =
                        dataSource.getConnection();

                PreparedStatement statement =
                        connection.prepareStatement(sql);

                ResultSet resultSet =
                        statement.executeQuery()
        ) {

            while (resultSet.next()) {

                String id = resultSet.getString("id");
                String content = resultSet.getString("content");

                Map<String, Object> metadata =
                        parseMetadata(
                                resultSet.getString("metadata")
                        );

                rows.add(
                        new Bm25Row(
                                id,
                                content,
                                String.valueOf(
                                        metadata.getOrDefault(
                                                "document_id",
                                                id
                                        )
                                ),
                                parseInt(
                                        metadata.get("chunk_index"),
                                        0
                                ),
                                String.valueOf(
                                        metadata.getOrDefault(
                                                "source",
                                                ""
                                        )
                                ),
                                String.valueOf(
                                        metadata.getOrDefault(
                                                "section",
                                                ""
                                        )
                                ),
                                String.valueOf(
                                        metadata.getOrDefault(
                                                "file_path",
                                                ""
                                        )
                                ),
                                String.valueOf(
                                        metadata.getOrDefault(
                                                "document_type",
                                                ""
                                        )
                                ),
                                parseInt(
                                        metadata.get("total_chunks"),
                                        0
                                )
                        )
                );
            }

        } catch (Exception e) {

            throw new RuntimeException(
                    "BM25读取知识库失败",
                    e
            );
        }

        return rows;
    }

    /**
     * 解析 PostgreSQL metadata JSON
     */
    private Map<String, Object> parseMetadata(
            String metadataJson) {

        if (metadataJson == null ||
                metadataJson.isBlank()) {

            return Collections.emptyMap();
        }

        try {

            return objectMapper.readValue(
                    metadataJson,
                    new TypeReference<>() {
                    }
            );

        } catch (Exception e) {

            throw new RuntimeException(
                    "BM25解析metadata失败: "
                            + metadataJson,
                    e
            );
        }
    }

    /**
     * 安全解析整数
     */
    private int parseInt(
            Object value,
            int defaultValue) {

        if (value == null) {
            return defaultValue;
        }

        try {

            return Integer.parseInt(
                    value.toString()
            );

        } catch (NumberFormatException e) {

            return defaultValue;
        }
    }

    /**
     * 使用 HanLP 词典分词的 Tokenizer。
     *
     * 相比早期的单字切分，词典分词可以：
     * - 把"分布式锁"切为完整词，而不是 四/布/斯/式/锁 等单字，
     *   显著降低跨主题的字面撞车；
     * - 让"的/是/什么"等虚词成为独立高词频词，
     *   由 IDF 自动压低其权重；
     * - 保留英文术语、数字的完整匹配（Redis、ThreadLocal）。
     *
     * 过滤规则：仅丢弃空白和不含字母数字的纯标点 token。
     */
    private List<String> tokenize(String text) {

        if (text == null || text.isBlank()) {
            return Collections.emptyList();
        }

        String normalized =
                text.toLowerCase(Locale.ROOT);

        List<String> tokens =
                new ArrayList<>();

        for (com.hankcs.hanlp.seg.common.Term term
                : com.hankcs.hanlp.HanLP.segment(normalized)) {

            String word = term.word;

            if (word == null || word.isBlank()) {
                continue;
            }

            boolean hasLetterOrDigit =
                    word.chars()
                            .anyMatch(Character::isLetterOrDigit);

            if (!hasLetterOrDigit) {
                continue;
            }

            tokens.add(word);
        }

        return tokens;
    }

    /**
     * 将内部表示转换为 Spring AI Document。
     *
     * 保留原始 metadata，
     * 特别是 section，
     * 否则 section-level evaluation 无法判断
     * BM25 是否检索到了正确知识章节。
     */
    private Document toSpringDocument(
            IndexedDocument document,
            double score) {

        Map<String, Object> metadata =
                new HashMap<>();

        metadata.put("id", document.id());
        metadata.put("document_id", document.documentId());
        metadata.put("chunk_index", document.chunkIndex());
        metadata.put("source", document.source());
        metadata.put("section", document.section());
        metadata.put("file_path", document.filePath());
        metadata.put("document_type", document.documentType());
        metadata.put("total_chunks", document.totalChunks());
        metadata.put("bm25_score", score);
        metadata.put("retrieval_source", "bm25");

        return new Document(
                document.content(),
                metadata
        );
    }

    /**
     * 不可变的 BM25 索引快照。
     */
    private record Bm25Index(
            List<IndexedDocument> documents,
            Map<String, List<Posting>> postings,
            double avgDocLength,
            int documentCount
    ) {
    }

    /**
     * 倒排表中的一条记录：某文档包含某词项的次数。
     */
    private record Posting(
            int documentIndex,
            int termFrequency
    ) {
    }

    /**
     * 索引中的一个文档。
     */
    private record IndexedDocument(
            String id,
            String content,
            String documentId,
            int chunkIndex,
            String source,
            String section,
            String filePath,
            String documentType,
            int totalChunks,
            int length
    ) {
    }

    /**
     * 从数据库读出的原始行。
     */
    private record Bm25Row(
            String id,
            String content,
            String documentId,
            int chunkIndex,
            String source,
            String section,
            String filePath,
            String documentType,
            int totalChunks
    ) {
    }
}
