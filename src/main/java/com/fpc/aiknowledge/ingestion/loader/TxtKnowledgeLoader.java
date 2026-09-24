package com.fpc.aiknowledge.ingestion.loader;

import com.fpc.aiknowledge.ingestion.model.KnowledgeDocument;
import org.springframework.stereotype.Component;

import java.nio.charset.CharacterCodingException;
import java.nio.charset.Charset;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.Map;

/**
 * 纯文本 (.txt) 知识文档 Loader。
 *
 * 设计目标：对"不规则 txt"具备容错能力，包括：
 *
 * 1. 编码不确定：
 *    优先按 UTF-8 严格解码，失败后回退 GBK，
 *    仍失败则按 UTF-8 宽松解码（非法字节替换为替换符），
 *    保证任何字节序列都能解析，不会抛出异常中断导入；
 * 2. 换行风格混合（\r\n / \n / \r）；
 * 3. 空文件、空白文件（抛出明确业务异常）。
 *
 * txt 没有结构信息，
 * 由 KnowledgeIngestionService 走通用段落切分。
 */
@Component
public class TxtKnowledgeLoader implements KnowledgeLoader {

    @Override
    public boolean supports(String source) {
        return source != null
                && source.toLowerCase().endsWith(".txt");
    }

    @Override
    public KnowledgeDocument load(String source) {

        Path path = Path.of(source)
                .toAbsolutePath()
                .normalize();

        if (!Files.exists(path)) {
            throw new IllegalArgumentException(
                    "TXT文件不存在：" + source);
        }

        if (!Files.isRegularFile(path)) {
            throw new IllegalArgumentException(
                    "指定路径不是文件：" + source);
        }

        byte[] bytes;

        try {
            bytes = Files.readAllBytes(path);
        } catch (Exception e) {
            throw new IllegalStateException(
                    "TXT读取失败：" + source, e);
        }

        String content = decode(bytes);

        if (content.isBlank()) {
            throw new IllegalArgumentException(
                    "TXT文件内容为空：" + source);
        }

        String documentId = path
                .toAbsolutePath()
                .normalize()
                .toString();

        Map<String, Object> metadata = new HashMap<>();

        metadata.put("document_id", documentId);
        metadata.put("source", path.getFileName().toString());
        metadata.put("file_path", path.toAbsolutePath().toString());
        metadata.put("document_type", "txt");
        metadata.put("charset", detectCharsetName(bytes));

        return new KnowledgeDocument(
                documentId,
                path.getFileName().toString(),
                "TXT",
                extractTitle(content, path),
                content,
                metadata
        );
    }

    /**
     * 解码策略：
     *
     * 1. UTF-8 严格解码（REPORT 遇到非法字节立即失败）；
     * 2. GBK 严格解码（覆盖中文 Windows 导出的常见编码）；
     * 3. UTF-8 宽松解码（REPLACE，任何输入都不会失败）。
     */
    private String decode(byte[] bytes) {

        try {
            return strictDecode(bytes, StandardCharsets.UTF_8);
        } catch (CharacterCodingException ignored) {
            // 尝试下一种编码
        }

        try {
            return strictDecode(bytes, Charset.forName("GBK"));
        } catch (CharacterCodingException ignored) {
            // 最终回退
        }

        return new String(bytes, StandardCharsets.UTF_8);
    }

    private String strictDecode(
            byte[] bytes,
            Charset charset)
            throws CharacterCodingException {

        return charset.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .decode(java.nio.ByteBuffer.wrap(bytes))
                .toString();
    }

    private String detectCharsetName(byte[] bytes) {

        try {
            strictDecode(bytes, StandardCharsets.UTF_8);
            return "UTF-8";
        } catch (CharacterCodingException ignored) {
            // 非 UTF-8
        }

        try {
            strictDecode(bytes, Charset.forName("GBK"));
            return "GBK";
        } catch (CharacterCodingException ignored) {
            // 无法确定
        }

        return "UTF-8(REPLACE)";
    }

    /**
     * 优先使用第一行非空短文本作为标题。
     */
    private String extractTitle(
            String content,
            Path path) {

        for (String line : content.split("\\R")) {

            String trimmed = line.trim();

            if (trimmed.isEmpty()) {
                continue;
            }

            if (trimmed.length() <= 50) {
                return trimmed;
            }

            break;
        }

        return path.getFileName().toString();
    }
}
