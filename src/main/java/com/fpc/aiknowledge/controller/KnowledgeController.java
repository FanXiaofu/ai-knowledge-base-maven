package com.fpc.aiknowledge.controller;

import com.fpc.aiknowledge.service.KnowledgeIngestionService;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/knowledge")
public class KnowledgeController {

    /**
     * 默认知识目录：项目根目录下的 knowledge 子目录。
     *
     * 使用相对路径，相对进程工作目录解析
     * （启动脚本会先切到项目根目录），
     * 这样项目整体搬迁后无需改代码。
     */
    private static final String DEFAULT_KNOWLEDGE_PATH =
            "knowledge";

    private final KnowledgeIngestionService ingestionService;

    public KnowledgeController(
            KnowledgeIngestionService ingestionService) {
        this.ingestionService = ingestionService;
    }

    @PostMapping("/import")
    public String importDocument(
            @RequestParam String path) {

        try {
            int chunks = ingestionService.ingest(path);
            return "文档导入成功，共生成 " + chunks + " 个文本块";
        } catch (Exception e) {
            return "文档导入失败：" + e.getMessage();
        }
    }

    /**
     * 批量导入知识目录。
     *
     * 默认导入项目下的 knowledge 目录（自建语料），
     * 可通过 dir 参数指定其他目录，
     * 例如导入官方文档语料 knowledge-official。
     */
    @PostMapping("/import-all")
    public String importAll(
            @RequestParam(
                    required = false
            ) String dir) {

        try {

            String knowledgePath =
                    (dir == null || dir.isBlank())
                            ? DEFAULT_KNOWLEDGE_PATH
                            : dir;

            int chunks =
                    ingestionService.ingestDirectory(knowledgePath);

            return "知识库批量导入成功，共生成 "
                    + chunks
                    + " 个文本块";

        } catch (Exception e) {
            return "知识库批量导入失败：" + e.getMessage();
        }
    }
}