package com.fpc.aiknowledge.ingestion.loader;

import com.fpc.aiknowledge.ingestion.model.KnowledgeDocument;
import org.springframework.stereotype.Component;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.Map;

@Component
public class MarkdownKnowledgeLoader
        implements KnowledgeLoader {

    @Override
    public boolean supports(String source) {

        return source != null
                && source.toLowerCase()
                        .endsWith(".md");
    }

    @Override
    public KnowledgeDocument load(
            String source) throws Exception {

        Path path = Path.of(source);

        if (!Files.exists(path)) {
            throw new IllegalArgumentException(
                    "文件不存在：" + source
            );
        }

        if (!Files.isRegularFile(path)) {
            throw new IllegalArgumentException(
                    "指定路径不是文件：" + source
            );
        }

        String content = Files.readString(
                path,
                StandardCharsets.UTF_8
        );

        if (content.isBlank()) {
            throw new IllegalArgumentException(
                    "文档内容不能为空：" + source
            );
        }

        String documentId = path
                .toAbsolutePath()
                .normalize()
                .toString();

        Map<String, Object> metadata =
                new HashMap<>();

        metadata.put(
                "document_id",
                documentId
        );

        metadata.put(
                "source",
                path.getFileName().toString()
        );

        metadata.put(
                "file_path",
                path.toAbsolutePath().toString()
        );

        metadata.put(
                "document_type",
                "markdown"
        );

        return new KnowledgeDocument(
                documentId,
                path.getFileName().toString(),
                "MARKDOWN",
                extractTitle(content, path),
                content,
                metadata
        );
    }

    /**
     * 优先使用 Markdown 一级标题作为文档标题。
     */
    private String extractTitle(
            String content,
            Path path) {

        for (String line : content.split("\\R")) {

            String trimmed = line.trim();

            if (trimmed.matches("^#\\s+.+$")) {

                return trimmed
                        .substring(1)
                        .trim();
            }
        }

        return path.getFileName().toString();
    }
}