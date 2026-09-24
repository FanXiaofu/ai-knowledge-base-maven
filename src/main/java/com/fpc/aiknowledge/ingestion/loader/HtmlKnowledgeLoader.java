package com.fpc.aiknowledge.ingestion.loader;

import com.fpc.aiknowledge.ingestion.image.ImageUtils;
import com.fpc.aiknowledge.ingestion.model.DocumentImage;
import com.fpc.aiknowledge.ingestion.model.KnowledgeDocument;
import org.jsoup.Jsoup;
import org.jsoup.nodes.Document;
import org.jsoup.nodes.Element;
import org.springframework.stereotype.Component;

import java.io.File;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * HTML (.html/.htm) 知识文档 Loader。
 *
 * 基于 Jsoup 解析，对"不规则 HTML"具备天然容错能力：
 *
 * 1. 标签未闭合、大小写混乱、属性不完整 —— Jsoup 宽容解析；
 * 2. 缺少 &lt;head&gt;/&lt;body&gt; 结构 —— 自动补全；
 * 3. 混乱嵌套的 div/span —— 递归下钻提取文本；
 * 4. &lt;script&gt;/&lt;style&gt;/注释 —— 自动忽略；
 * 5. charset 声明缺失或错误 —— Jsoup 自动探测 + 默认回退。
 *
 * 针对真实文档站点的额外处理：
 * 官方文档页面里正文之外的导航、侧边目录动辄数百条链接，
 * 因此先定位正文容器（article/main），
 * 再跳过 nav/header/footer/aside 等结构性元素。
 *
 * 输出归一化：
 *
 * - h1~h6 标题 → "## 标题" / "### 标题"，
 *   与 Markdown 知识文档共享同一套结构化切分逻辑；
 * - &lt;p&gt;/&lt;li&gt; → 文本行；
 * - &lt;table&gt; → 每行 "单元格 | 单元格 | ..."；
 * - &lt;pre&gt; → 保留原始文本。
 */
@Component
public class HtmlKnowledgeLoader implements KnowledgeLoader {

    /**
     * 单个 HTML 文档最多处理的图片数量。
     */
    private static final int MAX_IMAGES_PER_DOCUMENT = 8;

    /**
     * 单张图片的字节上限，超出视为照片级大图，跳过。
     */
    private static final long MAX_IMAGE_BYTES = 3L * 1024 * 1024;

    @Override
    public boolean supports(String source) {

        String lower = source == null
                ? ""
                : source.toLowerCase();

        return lower.endsWith(".html")
                || lower.endsWith(".htm");
    }

    @Override
    public KnowledgeDocument load(String source) {

        Path path = Path.of(source)
                .toAbsolutePath()
                .normalize();

        File file = path.toFile();

        if (!file.exists()) {
            throw new IllegalArgumentException(
                    "HTML文件不存在: " + path);
        }

        if (!file.isFile()) {
            throw new IllegalArgumentException(
                    "HTML路径不是文件: " + path);
        }

        Document document;

        try {

            /*
             * Jsoup 自动处理：
             * - 未闭合标签、错误嵌套；
             * - meta charset 探测（缺失时使用 UTF-8 默认值）。
             */
            document = Jsoup.parse(file, "UTF-8");

        } catch (Exception e) {
            throw new IllegalStateException(
                    "HTML解析失败: " + path, e);
        }

        Element contentRoot =
                selectContentRoot(document, document.body());

        String content = extractBodyText(contentRoot);

        if (content.isBlank()) {
            throw new IllegalArgumentException(
                    "HTML没有提取到有效文本内容: " + path);
        }

        String documentId = path.toString();

        Map<String, Object> metadata = new LinkedHashMap<>();

        metadata.put("document_id", documentId);
        metadata.put("source", file.getName());
        metadata.put("file_path", documentId);
        metadata.put("document_type", "html");

        /*
         * 抽取正文中的插图。
         * 官方文档的配图多为架构示意图，
         * 由视觉模型转成文字后可被检索。
         */
        List<DocumentImage> images =
                extractImages(contentRoot, file);

        if (!images.isEmpty()) {
            metadata.put("image_count", images.size());
        }

        String title = document.title();

        if (title == null || title.isBlank()) {
            title = extractTitle(content, file);
        }

        KnowledgeDocument knowledgeDocument =
                new KnowledgeDocument(
                        documentId,
                        file.getName(),
                        "HTML",
                        title,
                        content,
                        metadata
                );

        knowledgeDocument.setImages(images);

        return knowledgeDocument;
    }

    /**
     * 抽取正文容器内的图片。
     *
     * 与爬虫场景的取舍：
     * - 只取正文容器内的图，跳过导航栏 logo 等；
     * - 文件名含 icon/logo/badge 等关键词的直接跳过；
     * - 远程图片受大小上限和单文档数量上限约束，
     *   避免个别文档拖垮整批导入；
     * - 下载或解码失败一律跳过，不影响正文。
     */
    private List<DocumentImage> extractImages(
            Element contentRoot,
            File htmlFile) {

        List<DocumentImage> images =
                new ArrayList<>();

        if (contentRoot == null) {
            return images;
        }

        int index = 0;

        for (Element img : contentRoot.select("img")) {

            if (images.size() >= MAX_IMAGES_PER_DOCUMENT) {
                break;
            }

            /*
             * absUrl 会结合页面里的 <base href> 解析相对路径，
             * 这样离线保存的页面也能找回原站图片地址。
             * 解析不到时退回原始属性值（通常是本地相对路径）。
             */
            String src = img.absUrl("src");

            if (src.isBlank()) {
                src = img.attr("src");
            }

            if (src.isBlank()) {
                src = img.absUrl("data-src");
            }

            if (src.isBlank()) {
                src = img.attr("data-src");
            }

            if (src.isBlank()) {
                continue;
            }

            if (looksLikeIcon(src)) {
                continue;
            }

            try {

                byte[] data = downloadImage(src, htmlFile);

                if (data == null || data.length == 0) {
                    continue;
                }

                int[] size = ImageUtils.readDimensions(data);

                if (size == null) {
                    continue;
                }

                DocumentImage documentImage =
                        new DocumentImage(
                                index++,
                                data,
                                guessMimeType(src),
                                size[0],
                                size[1],
                                null
                        );

                if (documentImage.isMeaningful()) {
                    images.add(documentImage);
                }

            } catch (Exception ignored) {

                /*
                 * 单张图片失败不影响其他图片。
                 */
            }
        }

        return images;
    }

    /**
     * 依据文件名特征跳过明显是图标的图片。
     */
    private boolean looksLikeIcon(String src) {

        String lower = src.toLowerCase();

        for (String hint : new String[]{
                "icon", "logo", "favicon", "badge",
                "sprite", "avatar", "button"
        }) {
            if (lower.contains(hint)) {
                return true;
            }
        }

        return false;
    }

    /**
     * 读取图片内容：支持远程 URL 与本地相对路径。
     */
    private byte[] downloadImage(
            String src,
            File htmlFile) {

        try {

            java.net.URI uri;

            if (src.startsWith("http://")
                    || src.startsWith("https://")) {

                uri = java.net.URI.create(src);

            } else if (src.startsWith("//")) {

                uri = java.net.URI.create("https:" + src);

            } else {

                /*
                 * 本地相对路径：相对于 HTML 文件所在目录。
                 */
                java.nio.file.Path localPath =
                        htmlFile.toPath()
                                .getParent()
                                .resolve(src)
                                .normalize();

                if (!java.nio.file.Files.exists(localPath)) {
                    return null;
                }

                return java.nio.file.Files
                        .readAllBytes(localPath);
            }

            java.net.HttpURLConnection connection =
                    (java.net.HttpURLConnection)
                            uri.toURL().openConnection();

            connection.setConnectTimeout(10_000);
            connection.setReadTimeout(15_000);
            connection.setRequestProperty(
                    "User-Agent",
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
            );

            try {

                if (connection.getResponseCode() != 200) {
                    return null;
                }

                /*
                 * 超过上限的图片直接放弃，
                 * 通常是照片或大图，不适合走视觉描述。
                 */
                if (connection.getContentLengthLong()
                        > MAX_IMAGE_BYTES) {
                    return null;
                }

                try (java.io.InputStream input =
                             connection.getInputStream()) {

                    byte[] data = input.readAllBytes();

                    if (data.length > MAX_IMAGE_BYTES) {
                        return null;
                    }

                    return data;
                }

            } finally {
                connection.disconnect();
            }

        } catch (Exception e) {

            return null;
        }
    }

    private String guessMimeType(String src) {

        String lower = src.toLowerCase();

        if (lower.contains(".png")) {
            return "image/png";
        }

        if (lower.contains(".gif")) {
            return "image/gif";
        }

        if (lower.contains(".webp")) {
            return "image/webp";
        }

        return "image/jpeg";
    }

    /**
     * 从正文根节点开始递归提取，输出归一化 Markdown 风格文本。
     */
    private String extractBodyText(Element root) {

        if (root == null) {
            return "";
        }

        StringBuilder content = new StringBuilder();

        for (Element child : root.children()) {
            appendElement(child, content);
        }

        return content
                .toString()
                .replaceAll("\\n{3,}", "\n\n")
                .trim();
    }

    /**
     * 定位正文容器。
     *
     * 优先级：
     * 1. 文本最长的 &lt;article&gt; —— 大多数技术文档用它承载正文；
     * 2. 文本最长的 &lt;main&gt;；
     * 3. 回退到 body（此时仍会跳过导航类元素）。
     *
     * 取"文本最长"而非第一个，是为了避开页面里用于弹窗、
     * 卡片等其他用途的小型 article/main。
     */
    private Element selectContentRoot(
            Document document,
            Element body) {

        Element best = null;

        for (String selector : new String[]{"article", "main"}) {

            for (Element candidate
                    : document.select(selector)) {

                if (best == null
                        || candidate.text().length()
                        > best.text().length()) {

                    best = candidate;
                }
            }

            /*
             * article 命中即不再看 main：
             * main 通常把侧边导航也包在里面。
             */
            if (best != null) {
                break;
            }
        }

        return best != null ? best : body;
    }

    /**
     * 判断元素是否属于导航类噪音。
     *
     * 除了按标签名过滤（nav/header/footer/aside），
     * 还按 class/id 里的语义关键词过滤，
     * 因为很多站点用普通 div 承载侧边栏。
     */
    private boolean isNavigationElement(
            Element element) {

        String marker = (
                safeAttr(element.id())
                        + " "
                        + safeAttr(element.className())
        ).toLowerCase();

        if (marker.isBlank()) {
            return false;
        }

        for (String hint : new String[]{
                "nav", "menu", "sidebar", "side-bar",
                "toc", "breadcrumb", "footer", "header",
                "toolbar", "pagination", "pager"
        }) {
            if (marker.contains(hint)) {
                return true;
            }
        }

        return false;
    }

    private String safeAttr(String value) {
        return value == null ? "" : value;
    }

    private void appendElement(
            Element element,
            StringBuilder content) {

        String tagName = element.tagName().toLowerCase();

        /*
         * 忽略与正文无关的部分。
         */
        if (tagName.equals("script")
                || tagName.equals("style")
                || tagName.equals("noscript")
                || tagName.equals("template")
                || tagName.equals("form")
                || tagName.equals("button")
                || tagName.equals("select")
                || tagName.equals("option")
                || tagName.equals("svg")) {
            return;
        }

        /*
         * 结构化导航元素：
         * 官方文档站点的侧边目录、页头页脚通常是
         * 数百条链接的列表，不排除会淹没正文。
         */
        if (tagName.equals("nav")
                || tagName.equals("header")
                || tagName.equals("footer")
                || tagName.equals("aside")) {
            return;
        }

        if (isNavigationElement(element)) {
            return;
        }

        /*
         * 标题 → Markdown 标题。
         * h1 → "## "，h2 及以下 → "### "。
         */
        if (tagName.matches("h[1-6]")) {

            String text = element.text().trim();

            if (!text.isEmpty()) {

                String prefix =
                        tagName.equals("h1") ? "## " : "### ";

                content.append(prefix)
                        .append(text)
                        .append("\n\n");
            }

            return;
        }

        /*
         * 段落与列表项 → 文本行。
         */
        if (tagName.equals("p") || tagName.equals("li")) {

            String text = element.text().trim();

            if (!text.isEmpty()) {
                content.append(text).append("\n\n");
            }

            return;
        }

        /*
         * 预格式化文本 → 保留换行原样输出。
         */
        if (tagName.equals("pre")) {

            String text = element.wholeText().trim();

            if (!text.isEmpty()) {
                content.append(text).append("\n\n");
            }

            return;
        }

        /*
         * 表格 → 逐行 "单元格 | 单元格"。
         * 兼容不规整表格：缺失单元格、空单元格、错误嵌套。
         */
        if (tagName.equals("table")) {

            String tableText = toTableText(element);

            if (!tableText.isEmpty()) {
                content.append(tableText).append("\n\n");
            }

            return;
        }

        /*
         * 其他容器标签（div/section/article/ul/ol 等）
         * → 递归下钻；叶子容器直接输出聚合文本。
         */
        if (element.children().isEmpty()) {

            String text = element.ownText().trim();

            if (text.isEmpty()) {

                /*
                 * ownText 为空但包含换行分隔的文本节点时，
                 * 退化为 element.text()。
                 */
                text = element.text().trim();
            }

            if (!text.isEmpty()) {
                content.append(text).append("\n\n");
            }

            return;
        }

        for (Element child : element.children()) {
            appendElement(child, content);
        }
    }

    private String toTableText(Element table) {

        StringBuilder tableText = new StringBuilder();

        for (Element row : table.select("tr")) {

            StringBuilder rowText = new StringBuilder();

            for (Element cell : row.select("th, td")) {

                String cellText = cell.text().trim();

                rowText.append(cellText).append(" | ");
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
     * 优先使用第一个标题，否则第一个非空、非表格行。
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
