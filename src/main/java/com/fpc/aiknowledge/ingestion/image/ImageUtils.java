package com.fpc.aiknowledge.ingestion.image;

import javax.imageio.ImageIO;
import java.awt.Graphics2D;
import java.awt.RenderingHints;
import java.awt.image.BufferedImage;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;

/**
 * 图片处理工具。
 *
 * 真实文档里的图片尺寸差异极大，
 * 直接把原始大图交给视觉模型会导致
 * 单张推理耗时过长（实测 1.5MB 照片约 46 秒）。
 * 这里统一缩放到可控尺寸后再送模型。
 */
public final class ImageUtils {

    /**
     * 送入视觉模型前的最长边上限（像素）。
     */
    public static final int MAX_DIMENSION = 768;

    private ImageUtils() {
    }

    /**
     * 读取图片尺寸。
     *
     * 返回 null 表示无法识别（格式不支持或数据损坏）。
     */
    public static int[] readDimensions(byte[] data) {

        if (data == null || data.length == 0) {
            return null;
        }

        try {

            BufferedImage image = ImageIO.read(
                    new ByteArrayInputStream(data)
            );

            if (image == null) {
                return null;
            }

            return new int[]{
                    image.getWidth(),
                    image.getHeight()
            };

        } catch (Exception e) {

            return null;
        }
    }

    /**
     * 按最长边缩放图片；已经足够小或处理失败时返回原图。
     *
     * 缩放失败不影响导入流程，
     * 只是失去耗时优化。
     */
    public static byte[] resizeIfNeeded(
            byte[] data,
            int maxDimension) {

        if (data == null) {
            return new byte[0];
        }

        try {

            BufferedImage source = ImageIO.read(
                    new ByteArrayInputStream(data)
            );

            if (source == null) {
                return data;
            }

            int width = source.getWidth();
            int height = source.getHeight();

            int longest = Math.max(width, height);

            if (longest <= maxDimension) {
                return data;
            }

            double scale =
                    (double) maxDimension / longest;

            int targetWidth =
                    Math.max(1, (int) (width * scale));

            int targetHeight =
                    Math.max(1, (int) (height * scale));

            BufferedImage target = new BufferedImage(
                    targetWidth,
                    targetHeight,
                    BufferedImage.TYPE_INT_RGB
            );

            Graphics2D graphics = target.createGraphics();

            try {

                graphics.setRenderingHint(
                        RenderingHints.KEY_INTERPOLATION,
                        RenderingHints.VALUE_INTERPOLATION_BILINEAR
                );

                graphics.drawImage(
                        source,
                        0,
                        0,
                        targetWidth,
                        targetHeight,
                        null
                );

            } finally {
                graphics.dispose();
            }

            ByteArrayOutputStream output =
                    new ByteArrayOutputStream();

            ImageIO.write(target, "jpg", output);

            return output.toByteArray();

        } catch (Exception e) {

            return data;
        }
    }
}
