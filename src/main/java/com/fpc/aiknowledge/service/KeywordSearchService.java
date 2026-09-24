package com.fpc.aiknowledge.service;

import org.springframework.ai.document.Document;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

@Service
public class KeywordSearchService {

    private final JdbcTemplate jdbcTemplate;

    public KeywordSearchService(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    /**
     * 基于 PostgreSQL pg_trgm 的关键词/文本相似检索
     */
    public List<Document> search(String query, int topK) {

        String sql = """
                SELECT
                    id,
                    content,
                    metadata,
                    similarity(content, ?) AS keyword_score
                FROM vector_store
                WHERE content % ?
                ORDER BY keyword_score DESC
                LIMIT ?
                """;

        return jdbcTemplate.query(
                sql,
                (rs, rowNum) -> {

                    String id =
                            rs.getString("id");

                    String content =
                            rs.getString("content");

                    String metadataJson =
                            rs.getString("metadata");

                    double score =
                            rs.getDouble("keyword_score");

                    Map<String, Object> metadata =
                            new HashMap<>();

                    metadata.put(
                            "keyword_score",
                            score
                    );

                    metadata.put(
                            "retrieval_type",
                            "keyword"
                    );

                    metadata.put(
                            "source",
                            extractSource(metadataJson)
                    );

                    return Document.builder()
                            .id(id)
                            .text(content)
                            .metadata(metadata)
                            .build();
                },
                query,
                query,
                topK
        );
    }

    private String extractSource(
            String metadataJson) {

        if (metadataJson == null) {
            return "";
        }

        int index =
                metadataJson.indexOf(
                        "\"source\""
                );

        if (index < 0) {
            return "";
        }

        return metadataJson;
    }
}