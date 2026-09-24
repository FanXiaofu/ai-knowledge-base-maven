package com.fpc.aiknowledge.ingestion.loader;

import com.fpc.aiknowledge.ingestion.model.KnowledgeDocument;

public interface KnowledgeLoader {

    /**
     * 判断当前 Loader 是否支持指定数据源
     */
    boolean supports(String source);

    /**
     * 加载原始数据并转换成统一 KnowledgeDocument
     */
    KnowledgeDocument load(String source) throws Exception;
}