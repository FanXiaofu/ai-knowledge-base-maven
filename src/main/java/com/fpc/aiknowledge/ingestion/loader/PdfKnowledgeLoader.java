package com.fpc.aiknowledge.ingestion.loader;

import com.fpc.aiknowledge.ingestion.model.DocumentImage;
import com.fpc.aiknowledge.ingestion.model.KnowledgeDocument;
import org.apache.pdfbox.Loader;
import org.apache.pdfbox.cos.COSName;
import org.apache.pdfbox.pdmodel.PDDocument;
import org.apache.pdfbox.pdmodel.PDPage;
import org.apache.pdfbox.pdmodel.PDResources;
import org.apache.pdfbox.pdmodel.graphics.PDXObject;
import org.apache.pdfbox.pdmodel.graphics.image.PDImageXObject;
import org.apache.pdfbox.text.PDFTextStripper;
import org.springframework.stereotype.Component;

import javax.imageio.ImageIO;
import java.awt.image.BufferedImage;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.IOException;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@Component
public class PdfKnowledgeLoader implements KnowledgeLoader {

    @Override
    public boolean supports(String source) {
        return source != null
                && source.toLowerCase().endsWith(".pdf");
    }

    @Override
    public KnowledgeDocument load(String source) {

        Path path = Path.of(source)
                .toAbsolutePath()
                .normalize();

        File file = path.toFile();

        if (!file.exists()) {
            throw new IllegalArgumentException(
                    "PDF文件不存在: " + path);
        }

        if (!file.isFile()) {
            throw new IllegalArgumentException(
                    "PDF路径不是文件: " + path);
        }

        try (PDDocument document = Loader.loadPDF(file)) {

            PDFTextStripper stripper = new PDFTextStripper();

            StringBuilder content = new StringBuilder();

            int pageCount = document.getNumberOfPages();

            for (int page = 1; page <= pageCount; page++) {

                stripper.setStartPage(page);
                stripper.setEndPage(page);

                String pageText = stripper.getText(document);

                content.append("\n\n");
                content.append("===== PAGE ")
                        .append(page)
                        .append(" =====\n");

                content.append(pageText);
            }

            String title = extractTitle(file, content.toString());

            String documentId = path.toString();

            /*
             * 抽取页面中嵌入的图片。
             * 技术手册里的架构图、流程图是正文之外的重要信息，
             * 后续由视觉模型转成文字描述入库。
             */
            List<DocumentImage> images = extractImages(document);

            Map<String, Object> metadata = new LinkedHashMap<>();

            metadata.put("document_id", documentId);
            metadata.put("source", file.getName());
            metadata.put("file_path", documentId);
            metadata.put("document_type", "pdf");
            metadata.put("page_count", pageCount);

            if (!images.isEmpty()) {
                metadata.put("image_count", images.size());
            }

            KnowledgeDocument knowledgeDocument =
                    new KnowledgeDocument(
                            documentId,
                            file.getName(),
                            "PDF",
                            title,
                            content.toString(),
                            metadata
                    );

            knowledgeDocument.setImages(images);

            return knowledgeDocument;

        } catch (IOException e) {
            throw new IllegalStateException(
                    "PDF解析失败: " + path, e);
        }
    }

    /**
     * 逐页抽取内嵌图片。
     *
     * 只处理页面资源里直接引用的 XObject，
     * 不做递归解包；单张图片解析失败时跳过，
     * 不影响其余图片和正文。
     */
    private List<DocumentImage> extractImages(
            PDDocument document) {

        List<DocumentImage> images =
                new ArrayList<>();

        int index = 0;

        for (int pageNumber = 1;
             pageNumber <= document.getNumberOfPages();
             pageNumber++) {

            PDPage page = document.getPage(pageNumber - 1);

            PDResources resources = page.getResources();

            if (resources == null) {
                continue;
            }

            for (COSName name : resources.getXObjectNames()) {

                try {

                    PDXObject xObject =
                            resources.getXObject(name);

                    if (!(xObject instanceof PDImageXObject image)) {
                        continue;
                    }

                    BufferedImage buffered = image.getImage();

                    if (buffered == null) {
                        continue;
                    }

                    ByteArrayOutputStream output =
                            new ByteArrayOutputStream();

                    ImageIO.write(buffered, "png", output);

                    DocumentImage documentImage =
                            new DocumentImage(
                                    index++,
                                    output.toByteArray(),
                                    "image/png",
                                    buffered.getWidth(),
                                    buffered.getHeight(),
                                    pageNumber
                            );

                    /*
                     * 过滤掉图标、线条等装饰性小图。
                     */
                    if (documentImage.isMeaningful()) {
                        images.add(documentImage);
                    }

                } catch (Exception ignored) {

                    /*
                     * 不规则 PDF 中个别图片可能无法解码，
                     * 跳过即可。
                     */
                }
            }
        }

        return images;
    }

    private String extractTitle(File file, String content) {

        String[] lines = content.split("\\R");

        for (String line : lines) {

            String text = line.trim();

            if (text.isEmpty()) {
                continue;
            }

            if (text.startsWith("=====")) {
                continue;
            }

            return text;
        }

        return file.getName();
    }
}