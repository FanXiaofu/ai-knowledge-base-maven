package com.fpc.aiknowledge.ingestion.model;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class KnowledgeDocument {

    /**
     * 文档唯一标识
     */
    private String documentId;

    /**
     * 原始来源
     * 例如：
     * java.md
     * xxx.pdf
     * https://xxx.com/xxx
     */
    private String source;

    /**
     * 数据来源类型
     * MARKDOWN / PDF / WORD / WEB ...
     */
    private String sourceType;

    /**
     * 文档标题
     */
    private String title;

    /**
     * 文档正文
     */
    private String content;

    /**
     * 文档级 Metadata
     */
    private Map<String, Object> metadata = new HashMap<>();

    /**
     * 文档中提取出的图片。
     *
     * 由各 Loader 在解析时填充，
     * 入库阶段交给视觉模型生成描述后作为 chunk 写入。
     */
    private List<DocumentImage> images = new ArrayList<>();

    public KnowledgeDocument() {
    }

    public KnowledgeDocument(
            String documentId,
            String source,
            String sourceType,
            String title,
            String content,
            Map<String, Object> metadata) {

        this.documentId = documentId;
        this.source = source;
        this.sourceType = sourceType;
        this.title = title;
        this.content = content;

        if (metadata != null) {
            this.metadata.putAll(metadata);
        }
    }

    public String getDocumentId() {
        return documentId;
    }

    public void setDocumentId(String documentId) {
        this.documentId = documentId;
    }

    public String getSource() {
        return source;
    }

    public void setSource(String source) {
        this.source = source;
    }

    public String getSourceType() {
        return sourceType;
    }

    public void setSourceType(String sourceType) {
        this.sourceType = sourceType;
    }

    public String getTitle() {
        return title;
    }

    public void setTitle(String title) {
        this.title = title;
    }

    public String getContent() {
        return content;
    }

    public void setContent(String content) {
        this.content = content;
    }

    public Map<String, Object> getMetadata() {
        return metadata;
    }

    public void setMetadata(Map<String, Object> metadata) {
        this.metadata = metadata;
    }

    public List<DocumentImage> getImages() {
        return images;
    }

    public void setImages(List<DocumentImage> images) {
        this.images = images == null
                ? new ArrayList<>()
                : images;
    }
}