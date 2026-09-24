package com.fpc.aiknowledge.ingestion.loader;

import com.fpc.aiknowledge.ingestion.image.ImageUtils;
import com.fpc.aiknowledge.ingestion.model.DocumentImage;
import com.fpc.aiknowledge.ingestion.model.KnowledgeDocument;
import org.apache.poi.xwpf.usermodel.IBodyElement;
import org.apache.poi.xwpf.usermodel.XWPFDocument;
import org.apache.poi.xwpf.usermodel.XWPFParagraph;
import org.apache.poi.xwpf.usermodel.XWPFPictureData;
import org.apache.poi.xwpf.usermodel.XWPFRun;
import org.apache.poi.xwpf.usermodel.XWPFStyle;
import org.apache.poi.xwpf.usermodel.XWPFTable;
import org.apache.poi.xwpf.usermodel.XWPFTableCell;
import org.apache.poi.xwpf.usermodel.XWPFTableRow;
import org.springframework.stereotype.Component;

import java.io.File;
import java.io.FileInputStream;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Word (.docx) 知识文档 Loader。
 *
 * 设计目标：对"不规则 docx"具备容错能力，包括：
 *
 * 1. 文档缺少 styles.xml 或样式部件异常；
 * 2. 段落引用了未定义的样式 ID；
 * 3. 段落中存在空 Run、空段落、图片、特殊字符；
 * 4. 表格结构不规整（行列数量不一致、空单元格）；
 * 5. 单个元素解析失败时只跳过该元素，不影响整个文档。
 *
 * 输出归一化：
 *
 * - 识别出的标题段落 → "## 标题" / "### 标题"，
 *   与 Markdown 知识文档共享同一套结构化切分逻辑；
 * - 普通段落 → 按原文输出；
 * - 表格 → 每行输出为 "单元格 | 单元格 | ..."；
 * - 没有任何标题样式的文档输出为纯文本，
 *   由 KnowledgeIngestionService 走通用段落切分。
 */
@Component
public class DocxKnowledgeLoader implements KnowledgeLoader {

    /**
     * OOXML 内置标题样式 ID：Heading1 ~ Heading6。
     */
    private static final Pattern HEADING_STYLE_ID =
            Pattern.compile("(?i)^heading([1-9])$");

    /**
     * 样式名称匹配（中英文 Word 模板）：
     * "heading 1" / "Heading1" / "标题 1" / "标题1"
     */
    private static final Pattern HEADING_STYLE_NAME =
            Pattern.compile("(?i)^(?:heading|标题)\\s*([1-9])$");

    @Override
    public boolean supports(String source) {
        return source != null
                && source.toLowerCase().endsWith(".docx");
    }

    @Override
    public KnowledgeDocument load(String source) {

        Path path = Path.of(source)
                .toAbsolutePath()
                .normalize();

        File file = path.toFile();

        if (!file.exists()) {
            throw new IllegalArgumentException(
                    "DOCX文件不存在: " + path);
        }

        if (!file.isFile()) {
            throw new IllegalArgumentException(
                    "DOCX路径不是文件: " + path);
        }

        StringBuilder content = new StringBuilder();

        int paragraphCount = 0;
        int tableCount = 0;

        try (FileInputStream fis = new FileInputStream(file);
             XWPFDocument document = new XWPFDocument(fis)) {

            /*
             * 按文档 Body 的原始顺序遍历段落与表格，
             * 保证输出的内容顺序与 Word 中一致。
             */
            for (IBodyElement element : document.getBodyElements()) {

                try {

                    if (element instanceof XWPFParagraph paragraph) {

                        String line =
                                toNormalizedLine(paragraph, document);

                        if (line == null) {
                            continue;
                        }

                        content.append(line).append("\n\n");
                        paragraphCount++;

                    } else if (element instanceof XWPFTable table) {

                        String tableText =
                                toTableText(table);

                        if (tableText.isBlank()) {
                            continue;
                        }

                        content.append(tableText).append("\n\n");
                        tableCount++;
                    }

                } catch (Exception elementError) {

                    /*
                     * 不规则文档：单个段落/表格解析失败时
                     * 跳过该元素，继续处理剩余内容。
                     */
                    System.out.println(
                            "DOCX元素解析失败，已跳过："
                                    + elementError.getMessage());
                }
            }

        } catch (Exception e) {
            throw new IllegalStateException(
                    "DOCX解析失败: " + path, e);
        }

        String text = normalizeContent(content.toString());

        if (text.isBlank()) {
            throw new IllegalArgumentException(
                    "DOCX没有提取到有效文本内容: " + path);
        }

        String documentId = path.toString();

        Map<String, Object> metadata = new LinkedHashMap<>();

        metadata.put("document_id", documentId);
        metadata.put("source", file.getName());
        metadata.put("file_path", documentId);
        metadata.put("document_type", "docx");
        metadata.put("paragraph_count", paragraphCount);
        metadata.put("table_count", tableCount);

        /*
         * 抽取文档内嵌图片（截图、示意图等）。
         * Word 没有页的概念，因此不记录页码，
         * 只保留文档内顺序。
         */
        List<DocumentImage> images = extractImages(file);

        if (!images.isEmpty()) {
            metadata.put("image_count", images.size());
        }

        KnowledgeDocument knowledgeDocument =
                new KnowledgeDocument(
                        documentId,
                        file.getName(),
                        "DOCX",
                        extractTitle(text, file),
                        text,
                        metadata
                );

        knowledgeDocument.setImages(images);

        return knowledgeDocument;
    }

    /**
     * 依据文件扩展名推导 MIME 类型。
     */
    private String guessMimeType(String extension) {

        if (extension == null) {
            return "image/png";
        }

        return switch (extension.toLowerCase()) {
            case "jpg", "jpeg" -> "image/jpeg";
            case "gif" -> "image/gif";
            case "bmp" -> "image/bmp";
            default -> "image/png";
        };
    }

    /**
     * 抽取 docx 内嵌图片。
     *
     * POI 把整篇文档的图片统一放在包资源里，
     * 用 getAllPictures 一次取出；
     * 尺寸通过解码字节流获得，
     * 无法解码的图片直接跳过。
     */
    private List<DocumentImage> extractImages(File file) {

        List<DocumentImage> images =
                new ArrayList<>();

        try (FileInputStream fis = new FileInputStream(file);
             XWPFDocument document = new XWPFDocument(fis)) {

            int index = 0;

            for (XWPFPictureData picture
                    : document.getAllPictures()) {

                try {

                    byte[] data = picture.getData();

                    if (data == null || data.length == 0) {
                        continue;
                    }

                    int[] size =
                            ImageUtils.readDimensions(data);

                    if (size == null) {
                        continue;
                    }

                    DocumentImage documentImage =
                            new DocumentImage(
                                    index++,
                                    data,
                                    guessMimeType(
                                            picture
                                                    .suggestFileExtension()
                                    ),
                                    size[0],
                                    size[1],
                                    null
                            );

                    if (documentImage.isMeaningful()) {
                        images.add(documentImage);
                    }

                } catch (Exception ignored) {

                    /*
                     * 个别图片损坏时跳过，不影响其他图片。
                     */
                }
            }

        } catch (Exception e) {

            /*
             * 图片抽取失败不影响正文导入，
             * 只是失去图片信息。
             */
            System.out.println(
                    "DOCX图片抽取失败，已跳过："
                            + file.getName()
                            + "，原因：" + e.getMessage()
            );
        }

        return images;
    }

    /**
     * 将段落转换为归一化文本行。
     *
     * 返回 null 表示该段落应被跳过（空段落等）。
     * 标题段落返回带 "## "/"### " 前缀的 Markdown 标题。
     */
    private String toNormalizedLine(
            XWPFParagraph paragraph,
            XWPFDocument document) {

        String text = safeParagraphText(paragraph);

        if (text == null || text.isBlank()) {
            return null;
        }

        text = text.replace('\u00A0', ' ').trim();

        int headingLevel =
                detectHeadingLevel(paragraph, document);

        if (headingLevel <= 0) {
            return text;
        }

        /*
         * 标题层级归一化：
         * 1 级 → "## "，其余 → "### "。
         * 与 Markdown 切分器共享 "##/### 为章节边界" 的约定。
         */
        String prefix =
                headingLevel == 1 ? "## " : "### ";

        return prefix + text;
    }

    /**
     * 逐 Run 读取段落文本，兼容：
     * - 空 Run；
     * - Run 内含图片、字段、脚注引用等非文本内容；
     * - 极端情况下 getText() 抛异常。
     */
    private String safeParagraphText(
            XWPFParagraph paragraph) {

        StringBuilder text = new StringBuilder();

        try {

            for (XWPFRun run : paragraph.getRuns()) {

                if (run == null) {
                    continue;
                }

                String runText = run.text();

                if (runText != null) {
                    text.append(runText);
                }
            }

        } catch (Exception e) {

            /*
             * 逐 Run 读取失败时，
             * 退化尝试段落级 getText()。
             */
            try {
                String fallback = paragraph.getText();

                return fallback;
            } catch (Exception ignored) {
                return null;
            }
        }

        if (text.isEmpty()) {
            return null;
        }

        return text.toString();
    }

    /**
     * 检测段落是否为标题，返回标题层级（1~9），非标题返回 0。
     *
     * 检测顺序：
     * 1. 样式 ID（Heading1 / 标题1 对应的 ID）；
     * 2. 样式名称（heading N / 标题 N）。
     *
     * 全程 Null 安全：
     * - styles.xml 缺失时 getStyles() 可能为 null；
     * - pStyle 引用未定义样式时 getStyle() 返回 null。
     */
    private int detectHeadingLevel(
            XWPFParagraph paragraph,
            XWPFDocument document) {

        String styleId = null;

        try {
            styleId = paragraph.getStyleID();
        } catch (Exception ignored) {
            return 0;
        }

        if (styleId == null || styleId.isBlank()) {
            return 0;
        }

        /*
         * 1. 直接匹配内置标题样式 ID。
         */
        Matcher idMatcher =
                HEADING_STYLE_ID.matcher(styleId.trim());

        if (idMatcher.matches()) {
            return Integer.parseInt(idMatcher.group(1));
        }

        /*
         * 2. 通过样式名称匹配。
         *    中文 Word 模板的标题样式 ID 通常是 "1"、"2"，
         *    只有名称能区分 "标题 1" 和普通自定义样式。
         */
        XWPFStyle style = null;

        try {
            if (document.getStyles() != null) {
                style = document.getStyles()
                        .getStyle(styleId);
            }
        } catch (Exception ignored) {
            return 0;
        }

        if (style == null) {
            return 0;
        }

        String styleName = style.getName();

        if (styleName == null || styleName.isBlank()) {
            return 0;
        }

        Matcher nameMatcher =
                HEADING_STYLE_NAME.matcher(styleName.trim());

        if (nameMatcher.matches()) {
            return Integer.parseInt(nameMatcher.group(1));
        }

        return 0;
    }

    /**
     * 将表格转换为文本。
     *
     * 兼容不规则表格：
     * - 行列数量不一致；
     * - 空单元格、合并单元格（缺失的 gridSpan 单元格返回 null）；
     * - 单元格内含嵌套元素。
     */
    private String toTableText(XWPFTable table) {

        StringBuilder tableText = new StringBuilder();

        for (XWPFTableRow row : table.getRows()) {

            if (row == null) {
                continue;
            }

            StringBuilder rowText = new StringBuilder();

            for (XWPFTableCell cell : row.getTableCells()) {

                String cellText = "";

                if (cell != null) {
                    try {
                        cellText = cell.getText();
                    } catch (Exception ignored) {
                        cellText = "";
                    }
                }

                if (cellText == null) {
                    cellText = "";
                }

                rowText
                        .append(cellText
                                .replace('\n', ' ')
                                .replace('\u00A0', ' ')
                                .trim())
                        .append(" | ");
            }

            String line = rowText.toString().trim();

            if (line.isBlank()) {
                continue;
            }

            tableText.append(line).append("\n");
        }

        return tableText.toString().trim();
    }

    /**
     * 收敛连续空行，清理零宽字符。
     */
    private String normalizeContent(String content) {

        return content
                .replace("\u200b", "")
                .replaceAll("\\n{3,}", "\n\n")
                .trim();
    }

    /**
     * 优先使用第一个标题作为文档标题，
     * 否则使用第一个非空段落，最后退化为文件名。
     */
    private String extractTitle(
            String content,
            File file) {

        for (String line : content.split("\\R")) {

            String trimmed = line.trim();

            if (trimmed.matches("^#{1,6}\\s+.+$")) {
                return trimmed
                        .replaceFirst("^#{1,6}\\s+", "")
                        .trim();
            }

            if (!trimmed.startsWith("|")
                    && !trimmed.isBlank()) {
                return trimmed;
            }
        }

        return file.getName();
    }
}
