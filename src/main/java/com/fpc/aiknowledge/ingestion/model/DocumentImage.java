package com.fpc.aiknowledge.ingestion.model;

/**
 * 文档中提取出的一张图片。
 *
 * 图片本身不直接进入向量库，
 * 而是由视觉模型生成中文描述后，
 * 以描述文本作为一个 chunk 入库，
 * 使"图里画了什么"也能被检索到。
 */
public class DocumentImage {

    /**
     * 过滤阈值：小于该字节数的图片通常是图标、分割线等装饰元素。
     */
    public static final int MIN_BYTES = 5 * 1024;

    /**
     * 过滤阈值：任一边小于该像素数的图片视为装饰元素。
     */
    public static final int MIN_DIMENSION = 100;

    private final int index;

    private final byte[] data;

    private final String mimeType;

    private final int width;

    private final int height;

    /**
     * PDF 的页码；其他文档类型为 null。
     */
    private final Integer pageNumber;

    /**
     * 视觉模型生成的中文描述，由 VisionCaptionService 填充。
     */
    private String caption;

    public DocumentImage(
            int index,
            byte[] data,
            String mimeType,
            int width,
            int height,
            Integer pageNumber) {

        this.index = index;
        this.data = data;
        this.mimeType = mimeType;
        this.width = width;
        this.height = height;
        this.pageNumber = pageNumber;
    }

    /**
     * 是否为有信息量的图片。
     *
     * 真实文档（尤其官方文档）里大量小图标、logo、
     * 分割线、社交按钮都属于噪音，
     * 不过滤会让视觉模型把时间全花在描述图标上。
     */
    public boolean isMeaningful() {

        if (data == null || data.length < MIN_BYTES) {
            return false;
        }

        return width >= MIN_DIMENSION
                && height >= MIN_DIMENSION;
    }

    public int getIndex() {
        return index;
    }

    public byte[] getData() {
        return data;
    }

    public String getMimeType() {
        return mimeType;
    }

    public int getWidth() {
        return width;
    }

    public int getHeight() {
        return height;
    }

    public Integer getPageNumber() {
        return pageNumber;
    }

    public String getCaption() {
        return caption;
    }

    public void setCaption(String caption) {
        this.caption = caption;
    }
}
