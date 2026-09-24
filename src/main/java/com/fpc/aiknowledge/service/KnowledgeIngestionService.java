package com.fpc.aiknowledge.service;

import com.fpc.aiknowledge.ingestion.loader.KnowledgeLoader;
import com.fpc.aiknowledge.ingestion.model.DocumentImage;
import com.fpc.aiknowledge.ingestion.model.KnowledgeDocument;
import org.springframework.ai.document.Document;
import org.springframework.ai.transformer.splitter.TokenTextSplitter;
import org.springframework.ai.vectorstore.VectorStore;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

@Service
public class KnowledgeIngestionService {

    private final VectorStore vectorStore;

    private final List<KnowledgeLoader> loaders;

    /**
     * 知识库内容变化后需要让 BM25 倒排索引失效重建。
     */
    private final Bm25Service bm25Service;

    /**
     * 图片理解服务（可选，未启用时跳过图片处理）。
     */
    private final VisionCaptionService visionCaptionService;

    @org.springframework.beans.factory.annotation.Value(
            "${knowledge.image.storage-path:data/images}")
    private String imageStoragePath;

    /**
     * 图片描述 chunk 的 section 标识。
     */
    private static final String IMAGE_SECTION = "图片描述";

    public KnowledgeIngestionService(
            VectorStore vectorStore,
            List<KnowledgeLoader> loaders,
            Bm25Service bm25Service,
            VisionCaptionService visionCaptionService) {

        this.vectorStore = vectorStore;
        this.loaders = loaders;
        this.bm25Service = bm25Service;
        this.visionCaptionService = visionCaptionService;
    }

    /**
     * 导入单个知识文档。
     *
     * 当前支持：
     * Markdown、PDF、DOCX、TXT、HTML
     */
    public int ingest(String source) throws Exception {

        // 1. 根据数据源选择 Loader
        KnowledgeLoader loader =
                findLoader(source);

        // 2. Loader 负责读取和解析
        KnowledgeDocument document =
                loader.load(source);

        // 3. 删除旧版本 Chunk
        vectorStore.delete(
                "document_id == '"
                        + document.getDocumentId()
                        + "'"
        );

        /*
         * 删除动作已经改变了知识库内容，
         * 立即让 BM25 索引失效，
         * 保证后续检索不会读到已删除的旧 chunk。
         */
        bm25Service.invalidate();

        // 4. 根据文档类型进行结构化切分
        List<Document> sections =
                splitDocument(document);

        if (sections.isEmpty()) {
            throw new IllegalArgumentException(
                    "文档没有找到有效内容：" + source
            );
        }

        // 5. TokenTextSplitter 二级切分
        TokenTextSplitter splitter =
                new TokenTextSplitter();

        List<Document> finalChunks =
                new ArrayList<>();

        for (Document section : sections) {

            List<Document> sectionChunks =
                    splitter.apply(
                            List.of(section)
                    );

            finalChunks.addAll(sectionChunks);
        }

        // 6. 增加 Chunk Metadata
        List<Document> indexedChunks =
                new ArrayList<>();

        for (int i = 0;
             i < finalChunks.size();
             i++) {

            Document chunk =
                    finalChunks.get(i);

            Map<String, Object> metadata =
                    new HashMap<>(
                            chunk.getMetadata()
                    );

            metadata.put(
                    "chunk_index",
                    i
            );

            metadata.put(
                    "total_chunks",
                    finalChunks.size()
            );

            indexedChunks.add(
                    new Document(
                            sanitizeText(
                                    chunk.getText()
                            ),
                            metadata
                    )
            );
        }

        // 7. 图片理解：把图片转成文字描述后一并入库
        indexedChunks.addAll(
                buildImageChunks(document)
        );

        // 8. 写入向量数据库
        vectorStore.add(indexedChunks);

        /*
         * 新内容已入库，索引失效，
         * 下次 BM25 查询时会基于最新语料重建。
         */
        bm25Service.invalidate();

        return indexedChunks.size();
    }

    /**
     * 为文档中的图片生成描述，构造可入库的 chunk。
     *
     * 关键约定：
     * 图片 chunk 必须携带与正文相同的 document_id，
     * 否则重新导入同一文档时，
     * 旧的图片 chunk 不会被删除，造成内容重复。
     *
     * 单张图片失败只跳过该图片，
     * 不影响正文和其他图片的导入。
     */
    private List<Document> buildImageChunks(
            KnowledgeDocument document) {

        List<Document> chunks =
                new ArrayList<>();

        List<DocumentImage> images =
                document.getImages();

        if (images == null || images.isEmpty()) {
            return chunks;
        }

        if (!visionCaptionService.isEnabled()) {
            return chunks;
        }

        /*
         * 先按内容去重，再限制数量。
         *
         * PDF 中同一张图（如架构示意图）常被多个页面的
         * 资源字典共同引用，逐页抽取会得到多份完全相同的图片。
         * 实测一本 30 页手册只含 3 张不同的图，
         * 不去重会被重复描述 20 次，既浪费算力又污染语料。
         */
        List<DocumentImage> uniqueImages =
                deduplicateImages(images);

        if (uniqueImages.size() < images.size()) {
            System.out.println(
                    "  图片去重："
                            + images.size()
                            + " 张 → "
                            + uniqueImages.size()
                            + " 张"
            );
        }

        int limit = Math.min(
                uniqueImages.size(),
                visionCaptionService.getMaxImagesPerDocument()
        );

        System.out.println(
                "开始理解图片：" + document.getSource()
                        + "，共 " + limit + " 张"
        );

        for (DocumentImage image
                : uniqueImages.subList(0, limit)) {

            try {

                long start = System.nanoTime();

                String caption =
                        visionCaptionService.caption(image);

                long elapsedMs =
                        (System.nanoTime() - start) / 1_000_000;

                image.setCaption(caption);

                /*
                 * 描述质量过滤：
                 * 网页里的二维码、关注引导图等装饰性图片
                 * 尺寸不满足小图阈值，但内容没有检索价值，
                 * 依据描述内容剔除，避免污染语料。
                 */
                if (isNoiseImage(caption)) {

                    System.out.println(
                            "  图片 " + (image.getIndex() + 1)
                                    + " 判定为装饰性内容，已跳过"
                    );

                    continue;
                }

                String imagePath =
                        storeImage(
                                document.getDocumentId(),
                                image
                        );

                Map<String, Object> metadata =
                        new HashMap<>(
                                document.getMetadata()
                        );

                /*
                 * 图片 chunk 使用独立 section，
                 * 避免与正文章节在评估中互相干扰。
                 */
                metadata.put("section", IMAGE_SECTION);
                metadata.put("content_type", "image_caption");
                metadata.put("image_index", image.getIndex());
                metadata.put("image_path", imagePath);

                if (image.getPageNumber() != null) {
                    metadata.put(
                            "page_number",
                            image.getPageNumber()
                    );
                }

                String text = buildImageText(
                        document,
                        image,
                        caption
                );

                chunks.add(
                        new Document(
                                sanitizeText(text),
                                metadata
                        )
                );

                System.out.println(
                        "  图片 " + (image.getIndex() + 1)
                                + " 描述完成（" + elapsedMs + " ms）："
                                + caption.substring(
                                        0,
                                        Math.min(40, caption.length())
                                ) + "..."
                );

            } catch (Exception e) {

                System.out.println(
                        "  图片 " + (image.getIndex() + 1)
                                + " 描述失败，已跳过："
                                + e.getMessage()
                );
            }
        }

        return chunks;
    }

    /**
     * 按图片内容去重，保留首次出现的顺序。
     *
     * 用 SHA-256 指纹判断内容是否相同，
     * 避免同一张图被重复描述和重复入库。
     */
    private List<DocumentImage> deduplicateImages(
            List<DocumentImage> images) {

        List<DocumentImage> unique =
                new ArrayList<>();

        java.util.Set<String> seenHashes =
                new java.util.HashSet<>();

        for (DocumentImage image : images) {

            String hash = sha256(image.getData());

            if (seenHashes.add(hash)) {
                unique.add(image);
            }
        }

        return unique;
    }

    private String sha256(byte[] data) {

        try {

            java.security.MessageDigest digest =
                    java.security.MessageDigest
                            .getInstance("SHA-256");

            byte[] hash = digest.digest(data);

            StringBuilder hex = new StringBuilder();

            for (byte b : hash) {
                hex.append(String.format("%02x", b));
            }

            return hex.toString();

        } catch (Exception e) {

            /*
             * 摘要计算失败时退化为按长度去重，
             * 至少能挡住明显的重复。
             */
            return "len:" + data.length;
        }
    }

    /**
     * 判断图片描述是否属于无检索价值的装饰性内容。
     *
     * 实测中文教程站点里大量出现二维码与关注引导图，
     * 它们的尺寸能通过小图过滤，但描述内容对问答毫无价值。
     * 这里按描述语义剔除——比按尺寸或网址过滤更通用。
     */
    private boolean isNoiseImage(String caption) {

        if (caption == null || caption.isBlank()) {
            return true;
        }

        String text = caption.toLowerCase();

        for (String hint : new String[]{
                "二维码", "扫码", "扫一扫", "微信", "公众号",
                "关注", "广告", "logo", "水印"
        }) {
            if (text.contains(hint)) {
                return true;
            }
        }

        /*
         * 描述过短说明模型没看到有效内容。
         */
        return caption.trim().length() < 12;
    }

    /**
     * 组装图片 chunk 的文本。
     *
     * 带上来源与页码，使检索结果能说明
     * "这段话描述的是哪个文档哪一页的图"。
     */
    private String buildImageText(
            KnowledgeDocument document,
            DocumentImage image,
            String caption) {

        StringBuilder text =
                new StringBuilder();

        text.append("【图片】")
                .append(document.getSource());

        if (image.getPageNumber() != null) {
            text.append(" 第")
                    .append(image.getPageNumber())
                    .append("页");
        }

        text.append("\n\n").append(caption);

        return text.toString();
    }

    /**
     * 把图片落盘，返回相对路径。
     *
     * 图片本身不进入向量库，只作为溯源附件保留，
     * chunk 元数据中的 image_path 指向该文件。
     */
    private String storeImage(
            String documentId,
            DocumentImage image) {

        try {

            String folderName = Integer.toHexString(
                    documentId.hashCode()
            );

            java.nio.file.Path folder =
                    java.nio.file.Path.of(
                            imageStoragePath,
                            folderName
                    );

            java.nio.file.Files.createDirectories(folder);

            String extension =
                    image.getMimeType() != null
                            && image.getMimeType().contains("png")
                            ? ".png"
                            : ".jpg";

            java.nio.file.Path target = folder.resolve(
                    "img_" + image.getIndex() + extension
            );

            java.nio.file.Files.write(
                    target,
                    image.getData()
            );

            return target.toString();

        } catch (Exception e) {

            /*
             * 落盘失败不影响检索，
             * 只是失去图片文件的溯源能力。
             */
            return "";
        }
    }

    /**
     * 清理无法写入 PostgreSQL text 类型的字符。
     *
     * 真实文档（尤其是从网页抽取的内容）可能包含
     * NUL(0x00) 等控制字符，直接入库会报
     * invalid byte sequence for encoding "UTF8"。
     *
     * 保留制表符、换行和回车，其余控制字符剔除。
     */
    private String sanitizeText(String text) {

        if (text == null) {
            return "";
        }

        return text
                .replace("\u0000", "")
                .replaceAll(
                        "[\\u0001-\\u0008"
                                + "\\u000B\\u000C"
                                + "\\u000E-\\u001F"
                                + "\\u007F]",
                        ""
                );
    }

    /**
     * 查找能够处理当前数据源的 Loader。
     */
    private KnowledgeLoader findLoader(
            String source) {

        return loaders.stream()
                .filter(loader ->
                        loader.supports(source))
                .findFirst()
                .orElseThrow(() ->
                        new IllegalArgumentException(
                                "暂不支持的数据源：" +
                                source
                        )
                );
    }

    /**
     * 根据数据源类型进行结构化切分。
     *
     * Markdown / DOCX / HTML
     *   → Loader 已归一化为 Markdown 风格文本，
     *     按 ##/### 标题切分；
     *     不规则文档（没有任何标题）退化为通用段落切分。
     *
     * PDF  → 页面
     * TXT  → 通用段落切分
     */
    private List<Document> splitDocument(
            KnowledgeDocument document) {

        if ("PDF".equals(
                document.getSourceType())) {

            return splitPdf(
                    document
            );
        }

        if ("MARKDOWN".equals(
                document.getSourceType())
                || "DOCX".equals(
                document.getSourceType())
                || "HTML".equals(
                document.getSourceType())) {

            List<Document> sections =
                    splitMarkdown(document);

            if (!sections.isEmpty()) {
                return sections;
            }

            /*
             * 不规则文档：
             * 没有任何标题结构，走通用段落切分。
             */
            return genericSplit(document);
        }

        if ("TXT".equals(
                document.getSourceType())) {

            return genericSplit(document);
        }

        throw new IllegalArgumentException(
                "暂不支持的文档类型：" +
                document.getSourceType()
        );
    }

    /**
     * 通用段落切分，用于没有结构信息的文档：
     * TXT、没有标题样式的不规则 DOCX / HTML 等。
     *
     * 策略：
     * 1. 逐行扫描，跳过空行；
     * 2. 连续段落累计到约 800 字符形成一个 Section；
     * 3. 超长段落交给后续 TokenTextSplitter 二级切分。
     */
    private List<Document> genericSplit(
            KnowledgeDocument document) {

        List<Document> documents =
                new ArrayList<>();

        String[] lines =
                document.getContent().split("\\R");

        StringBuilder current =
                new StringBuilder();

        int partIndex = 0;

        for (String line : lines) {

            String trimmed = line.trim();

            if (trimmed.isEmpty()) {
                continue;
            }

            current.append(line).append("\n");

            if (current.length() >= 800) {

                appendGenericSection(
                        document,
                        documents,
                        current.toString(),
                        ++partIndex
                );

                current = new StringBuilder();
            }
        }

        String remaining =
                current.toString().trim();

        if (!remaining.isEmpty()) {

            appendGenericSection(
                    document,
                    documents,
                    remaining,
                    ++partIndex
            );
        }

        if (documents.isEmpty()) {
            throw new IllegalArgumentException(
                    "文档没有提取到有效内容：" +
                            document.getSource()
            );
        }

        return documents;
    }

    private void appendGenericSection(
            KnowledgeDocument document,
            List<Document> documents,
            String content,
            int partIndex) {

        String text = content.trim();

        if (text.isEmpty()) {
            return;
        }

        Map<String, Object> metadata =
                new HashMap<>(
                        document.getMetadata()
                );

        metadata.put(
                "section",
                "第" + partIndex + "部分"
        );

        documents.add(
                new Document(
                        text,
                        metadata
                )
        );
    }

    /**
     * Markdown 二级标题切分。
     */
    private List<Document> splitMarkdown(
            KnowledgeDocument document) {

        List<MarkdownSection> sections =
                splitBySecondLevelHeading(
                        document.getContent()
                );

        List<Document> documents =
                new ArrayList<>();

        for (MarkdownSection section :
                sections) {

            Map<String, Object> metadata =
                    new HashMap<>(
                            document.getMetadata()
                    );

            metadata.put(
                    "section",
                    section.title()
            );

            documents.add(
                    new Document(
                            section.content(),
                            metadata
                    )
            );
        }

        return documents;
    }

    /**
     * PDF 按页切分。
     *
     * PdfKnowledgeLoader 会在文本中加入：
     *
     * ===== PAGE 1 =====
     * ===== PAGE 2 =====
     *
     * 这里根据页面标记进行切分，
     * 并把页码写入 Chunk Metadata。
     */
    private List<Document> splitPdf(
            KnowledgeDocument document) {

        List<Document> documents =
                new ArrayList<>();

        String content =
                document.getContent();

        String[] pages =
                content.split(
                        "(?m)(?=^===== PAGE \\d+ =====$)"
                );

        for (String page :
                pages) {

            String pageContent =
                    page.trim();

            if (pageContent.isBlank()) {
                continue;
            }

            int pageNumber =
                    extractPageNumber(
                            pageContent
                    );

            if (pageNumber <= 0) {
                continue;
            }

            // 删除页面标记，
            // 保留真正的 PDF 文本内容
            String text =
                    pageContent.replaceFirst(
                            "(?m)^===== PAGE \\d+ =====\\s*",
                            ""
                    ).trim();

            if (text.isBlank()) {
                continue;
            }

            Map<String, Object> metadata =
                    new HashMap<>(
                            document.getMetadata()
                    );

            metadata.put(
                    "page_number",
                    pageNumber
            );

            metadata.put(
                    "document_type",
                    "pdf"
            );

            documents.add(
                    new Document(
                            text,
                            metadata
                    )
            );
        }

        return documents;
    }

    /**
     * 从：
     *
     * ===== PAGE 12 =====
     *
     * 中提取页码。
     */
    private int extractPageNumber(
            String pageContent) {

        java.util.regex.Matcher matcher =
                java.util.regex.Pattern
                        .compile(
                                "^===== PAGE (\\d+) ====="
                        )
                        .matcher(
                                pageContent
                        );

        if (matcher.find()) {
            return Integer.parseInt(
                    matcher.group(1)
            );
        }

        return -1;
    }

    /**
     * 按 Markdown 标题切分。
     *
     * ## 与 ### 均作为章节边界，
     * 这样 DOCX / HTML 归一化后的多级标题
     * 也能参与结构化切分。
     */
    private List<MarkdownSection>
    splitBySecondLevelHeading(
            String content) {

        List<MarkdownSection> sections =
                new ArrayList<>();

        java.util.regex.Pattern headingPattern =
                java.util.regex.Pattern
                        .compile("^(#{2,})\\s+(.+)$");

        String[] lines =
                content.split("\\R");

        String currentTitle = null;

        StringBuilder currentContent =
                new StringBuilder();

        /*
         * 首个标题之前的正文内容。
         *
         * 不规则文档可能前半部分没有任何标题，
         * 直接丢弃会造成数据丢失，
         * 因此收集后作为独立的引言 Section 保留。
         */
        StringBuilder leadingContent =
                new StringBuilder();

        for (String line : lines) {

            String trimmed =
                    line.trim();

            java.util.regex.Matcher headingMatcher =
                    headingPattern.matcher(trimmed);

            if (headingMatcher.matches()) {

                // 保存上一个 Section 或引言
                if (currentTitle != null) {

                    saveSection(
                            sections,
                            currentTitle,
                            currentContent
                                    .toString()
                    );

                } else if (!leadingContent.isEmpty()) {

                    sections.add(
                            new MarkdownSection(
                                    leadingTitle(
                                            leadingContent
                                                    .toString()
                                    ),
                                    leadingContent
                                            .toString()
                                            .trim()
                            )
                    );
                }

                // 开始新的 Section
                currentTitle =
                        headingMatcher
                                .group(2)
                                .trim();

                currentContent =
                        new StringBuilder();

            } else {

                if (currentTitle != null) {

                    currentContent
                            .append(line)
                            .append("\n");

                } else {

                    /*
                     * 跳过文档主标题行（# 开头），
                     * 其余标题之前的正文全部保留。
                     */
                    if (trimmed.matches(
                            "^#\\s+.+$")) {
                        continue;
                    }

                    if (!trimmed.isEmpty()) {

                        leadingContent
                                .append(line)
                                .append("\n");
                    }
                }
            }
        }

        // 保存最后一个 Section 或引言
        if (currentTitle != null) {

            saveSection(
                    sections,
                    currentTitle,
                    currentContent
                            .toString()
            );

        } else if (!leadingContent.isEmpty()) {

            sections.add(
                    new MarkdownSection(
                            leadingTitle(
                                    leadingContent
                                            .toString()
                            ),
                            leadingContent
                                    .toString()
                                    .trim()
                    )
            );
        }

        return sections;
    }

    /**
     * 保存一个非空章节。
     */
    private void saveSection(
            List<MarkdownSection> sections,
            String title,
            String content) {

        String sectionContent =
                content.trim();

        if (sectionContent.isBlank()) {
            return;
        }

        sections.add(
                new MarkdownSection(
                        title,
                        title + "\n\n" + sectionContent
                )
        );
    }

    /**
     * 引言 Section 的标题：
     * 取第一行非空文本，截断到 40 字符。
     */
    private String leadingTitle(
            String leadingContent) {

        for (String line
                : leadingContent.split("\\R")) {

            String trimmed = line.trim();

            if (trimmed.isEmpty()) {
                continue;
            }

            return trimmed.length() <= 40
                    ? trimmed
                    : trimmed.substring(0, 40);
        }

        return "引言";
    }

    private record MarkdownSection(
            String title,
            String content
    ) {
    }

    /**
     * 批量导入知识目录。
     *
     * 当前支持：
     * Markdown、PDF、DOCX、TXT、HTML
     */
    public int ingestDirectory(
            String directoryPath) throws Exception {

        java.nio.file.Path directory =
                java.nio.file.Path.of(
                        directoryPath
                );

        if (!java.nio.file.Files.exists(
                directory)) {

            throw new IllegalArgumentException(
                    "知识库目录不存在：" +
                    directoryPath
            );
        }

        if (!java.nio.file.Files.isDirectory(
                directory)) {

            throw new IllegalArgumentException(
                    "指定路径不是目录：" +
                    directoryPath
            );
        }

        int totalChunks = 0;

        List<String> failedFiles =
                new ArrayList<>();

        try (var files =
                     java.nio.file.Files.list(
                             directory)) {

            List<java.nio.file.Path>
                    knowledgeFiles =
                    files
                            .filter(
                                    java.nio.file.Files
                                            ::isRegularFile
                            )
                            .filter(path -> {

                                String fileName =
                                        path.getFileName()
                                                .toString()
                                                .toLowerCase();

                                return fileName.endsWith(".md")
                                        || fileName.endsWith(".pdf")
                                        || fileName.endsWith(".docx")
                                        || fileName.endsWith(".txt")
                                        || fileName.endsWith(".html")
                                        || fileName.endsWith(".htm");
                            })
                            .sorted()
                            .toList();

            if (knowledgeFiles.isEmpty()) {

                throw new IllegalArgumentException(
                        "knowledge 目录中没有受支持的文档文件"
                );
            }

            for (var file :
                    knowledgeFiles) {

                String fileName =
                        file.getFileName().toString();

                System.out.println(
                        "正在导入知识文档：" + fileName
                );

                try {

                    int chunks =
                            ingest(
                                    file.toAbsolutePath()
                                            .toString()
                            );

                    totalChunks += chunks;

                    System.out.println(
                            "导入完成：" +
                                    fileName +
                                    "，生成 " +
                                    chunks +
                                    " 个 Chunk"
                    );

                } catch (Exception fileError) {

                    /*
                     * 真实文档质量参差不齐：
                     * 单个文档解析或入库失败时记录并继续，
                     * 不中断整批导入。
                     */
                    failedFiles.add(
                            fileName + "（"
                                    + fileError.getMessage()
                                    + "）"
                    );

                    System.out.println(
                            "导入失败，已跳过：" +
                                    fileName +
                                    "，原因：" +
                                    fileError.getMessage()
                    );
                }
            }
        }

        if (!failedFiles.isEmpty()) {

            System.out.println(
                    "本批次共 " + failedFiles.size()
                            + " 个文档导入失败："
            );

            for (String failed : failedFiles) {
                System.out.println("  - " + failed);
            }
        }

        return totalChunks;
    }
}