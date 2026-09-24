package com.fpc.aiknowledge.tool;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.ai.tool.annotation.Tool;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@Component
public class DocumentListTool {

    private final JdbcTemplate jdbcTemplate;

    /**
     * 当前项目没有将 ObjectMapper 注册为 Spring Bean，
     * 因此这里直接创建 ObjectMapper 用于解析 metadata JSON。
     */
    private final ObjectMapper objectMapper = new ObjectMapper();

    public DocumentListTool(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Tool(description = """
            查看知识库中当前已经收录的文档列表。
            当用户询问知识库有哪些文档、有哪些资料、
            支持哪些文档类型或想了解知识库内容范围时使用。
            """)
    public String listDocuments() {

        /*
         * 不使用 DISTINCT metadata。
         *
         * metadata 是 JSON 类型，PostgreSQL 对其执行 DISTINCT
         * 会导致 equality operator 相关的 SQL 错误。
         *
         * 后续在 Java 层根据 document_id / source 去重。
         */
        String sql = """
                SELECT metadata
                FROM vector_store
                WHERE metadata IS NOT NULL
                """;

        List<String> metadataList =
                jdbcTemplate.query(
                        sql,
                        (rs, rowNum) -> rs.getString("metadata")
                );

        if (metadataList.isEmpty()) {
            return "当前知识库中没有文档。";
        }

        /*
         * Key：
         * document_id
         *
         * Value：
         * 当前文档的基本信息
         *
         * 使用 LinkedHashMap 保持数据库查询后的文档顺序。
         */
        Map<String, Map<String, Object>> documents =
                new LinkedHashMap<>();

        for (String metadataJson : metadataList) {

            try {

                Map<String, Object> metadata =
                        objectMapper.readValue(
                                metadataJson,
                                new TypeReference<Map<String, Object>>() {
                                }
                        );

                /*
                 * 优先使用 document_id 作为文档唯一标识。
                 *
                 * 如果不存在 document_id，
                 * 则退化使用 source。
                 */
                String documentId =
                        String.valueOf(
                                metadata.getOrDefault(
                                        "document_id",
                                        metadata.getOrDefault(
                                                "source",
                                                "unknown"
                                        )
                                )
                        );

                /*
                 * 同一个文档通常对应多个 chunk，
                 * 因此这里只保留第一条 metadata。
                 */
                if (!documents.containsKey(documentId)) {

                    Map<String, Object> document =
                            new LinkedHashMap<>();

                    document.put(
                            "source",
                            metadata.getOrDefault(
                                    "source",
                                    "未知"
                            )
                    );

                    document.put(
                            "document_type",
                            metadata.getOrDefault(
                                    "document_type",
                                    "未知"
                            )
                    );

                    document.put(
                            "total_chunks",
                            metadata.getOrDefault(
                                    "total_chunks",
                                    "未知"
                            )
                    );

                    document.put(
                            "page_count",
                            metadata.getOrDefault(
                                    "page_count",
                                    null
                            )
                    );

                    documents.put(documentId, document);
                }

            } catch (Exception ignored) {
                /*
                 * 某一条 metadata JSON 解析失败时，
                 * 不影响其他正常文档。
                 */
            }
        }

        if (documents.isEmpty()) {
            return "知识库中存在文档，但无法读取文档信息。";
        }

        StringBuilder result =
                new StringBuilder();

        result.append("当前知识库共收录 ")
                .append(documents.size())
                .append(" 个文档：\n\n");

        int index = 1;

        for (Map<String, Object> document :
                documents.values()) {

            result.append("[")
                    .append(index++)
                    .append("] ");

            result.append("文档：")
                    .append(document.get("source"))
                    .append("\n");

            result.append("类型：")
                    .append(document.get("document_type"))
                    .append("\n");

            result.append("分块数量：")
                    .append(document.get("total_chunks"))
                    .append("\n");

            Object pageCount =
                    document.get("page_count");

            if (pageCount != null) {

                result.append("页数：")
                        .append(pageCount)
                        .append("\n");
            }

            result.append("\n");
        }

        return result.toString();
    }
}
