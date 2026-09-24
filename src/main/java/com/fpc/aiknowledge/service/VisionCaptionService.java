package com.fpc.aiknowledge.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fpc.aiknowledge.ingestion.image.ImageUtils;
import com.fpc.aiknowledge.ingestion.model.DocumentImage;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Base64;
import java.util.HashMap;
import java.util.Map;

/**
 * 图片理解服务。
 *
 * 调用 Ollama 的视觉模型，把文档中的图片转成中文描述，
 * 描述文本随后作为一个 chunk 进入向量库，
 * 使"图里画了什么"这类问题也能被检索到。
 *
 * 实现上直接调用 Ollama 的 /api/chat 接口
 * （与 RerankerClient 调用 Python 服务的方式一致），
 * 这样可以自由指定模型标签，
 * 而不受 Spring AI 内置模型枚举的限制。
 */
@Service
public class VisionCaptionService {

    private static final String OLLAMA_CHAT_URL =
            "http://localhost:11434/api/chat";

    /**
     * 描述图片的提示词。
     *
     * 要求中文、聚焦技术信息、不臆测，
     * 因为描述会直接进入检索语料。
     */
    private static final String CAPTION_PROMPT = """
            这是一张技术文档中的配图。请用中文描述它的内容，要求：

            1. 如果是架构图、流程图、时序图，说明它表达了什么结构或流程，包含哪些关键组件；
            2. 如果是表格截图，概括表格在对比什么、有哪些列；
            3. 如果是界面截图，说明这是什么界面、展示了什么操作；
            4. 如果是照片或装饰性图片，用一句话说明即可；
            5. 只描述你能看到的内容，不要推测和补充图中没有的信息；
            6. 直接输出描述，不要使用"这张图片展示了"之类的开场白。
            """;

    @Value("${knowledge.vision.enabled:true}")
    private boolean enabled;

    @Value("${knowledge.vision.model:qwen2.5vl:3b}")
    private String model;

    @Value("${knowledge.vision.max-images-per-document:20}")
    private int maxImagesPerDocument;

    private final HttpClient httpClient;

    private final ObjectMapper objectMapper;

    public VisionCaptionService() {

        this.httpClient = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_1_1)
                .connectTimeout(Duration.ofSeconds(10))
                .build();

        this.objectMapper = new ObjectMapper();
    }

    public boolean isEnabled() {
        return enabled;
    }

    public int getMaxImagesPerDocument() {
        return maxImagesPerDocument;
    }

    public String getModel() {
        return model;
    }

    /**
     * 生成图片描述。
     *
     * 调用失败时抛出异常，由调用方决定是否跳过该图片。
     */
    public String caption(DocumentImage image) throws Exception {

        /*
         * 统一缩放到可控尺寸再送模型：
         * 实测 1.5MB 的原图单张推理约 46 秒，
         * 缩放后可以显著降低耗时。
         */
        byte[] payload = ImageUtils.resizeIfNeeded(
                image.getData(),
                ImageUtils.MAX_DIMENSION
        );

        String base64 =
                Base64.getEncoder().encodeToString(payload);

        Map<String, Object> message = new HashMap<>();

        message.put("role", "user");
        message.put("content", CAPTION_PROMPT);
        message.put("images", new String[]{base64});

        Map<String, Object> request = new HashMap<>();

        request.put("model", model);
        request.put("messages", new Object[]{message});
        request.put("stream", false);

        String requestJson =
                objectMapper.writeValueAsString(request);

        HttpRequest httpRequest =
                HttpRequest.newBuilder()
                        .uri(URI.create(OLLAMA_CHAT_URL))
                        .timeout(Duration.ofSeconds(300))
                        .header(
                                "Content-Type",
                                "application/json; charset=UTF-8"
                        )
                        .POST(
                                HttpRequest.BodyPublishers
                                        .ofByteArray(
                                                requestJson.getBytes(
                                                        StandardCharsets.UTF_8
                                                )
                                        )
                        )
                        .build();

        HttpResponse<String> response =
                httpClient.send(
                        httpRequest,
                        HttpResponse.BodyHandlers.ofString(
                                StandardCharsets.UTF_8
                        )
                );

        if (response.statusCode() != 200) {

            throw new IllegalStateException(
                    "视觉模型返回 HTTP "
                            + response.statusCode()
            );
        }

        JsonNode root =
                objectMapper.readTree(response.body());

        JsonNode content =
                root.path("message").path("content");

        if (content.isMissingNode()
                || content.asText().isBlank()) {

            throw new IllegalStateException(
                    "视觉模型返回内容为空"
            );
        }

        return content.asText().trim();
    }
}
