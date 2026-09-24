package com.fpc.aiknowledge.service;

import com.fpc.aiknowledge.tool.DocumentListTool;
import com.fpc.aiknowledge.tool.KnowledgeSearchTool;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.model.ChatModel;
import org.springframework.ai.tool.method.MethodToolCallbackProvider;
import org.springframework.stereotype.Service;

import java.util.UUID;

@Service
public class ToolCallingService {

    private static final Logger log =
            LoggerFactory.getLogger(ToolCallingService.class);

    private final ChatClient chatClient;

    public ToolCallingService(
            ChatModel chatModel,
            KnowledgeSearchTool knowledgeSearchTool,
            DocumentListTool documentListTool) {

        MethodToolCallbackProvider toolCallbackProvider =
                MethodToolCallbackProvider.builder()
                        .toolObjects(
                                knowledgeSearchTool,
                                documentListTool
                        )
                        .build();

        this.chatClient = ChatClient.builder(chatModel)
                .defaultToolCallbacks(
                        toolCallbackProvider.getToolCallbacks()
                )
                .build();
    }

    public String chat(String question) {

        if (question == null || question.isBlank()) {
            throw new IllegalArgumentException("问题不能为空");
        }

        // 生成本次请求唯一 ID
        String requestId = UUID.randomUUID()
                .toString()
                .replace("-", "")
                .substring(0, 12);

        long startTime = System.nanoTime();

        log.info(
                "[AI-REQUEST] request_id={}, question={}",
                requestId,
                question
        );

        try {

            String answer = chatClient.prompt()
                    .system("""
                            你是一个技术知识助手。

                            你可以使用以下工具：

                            1. KnowledgeSearchTool：
                               用于搜索知识库中的具体技术内容。
                               当用户询问 Java、Spring、MySQL、Redis、RabbitMQ、
                               Docker 或其他可能存在于知识库中的具体技术问题时，
                               使用该工具。

                            2. DocumentListTool：
                               用于查看当前知识库已经收录了哪些文档。
                               当用户询问知识库有哪些资料、有哪些文档、
                               支持哪些内容时，使用该工具。

                            请根据用户问题选择合适的工具。

                            如果使用 KnowledgeSearchTool，
                            必须严格依据工具返回的内容回答，
                            不要编造知识库中不存在的信息。

                            如果知识库没有足够的信息，
                            应明确告诉用户知识库中没有足够的信息。

                            如果问题与知识库无关，
                            可以不调用工具直接回答。
                            """)
                    .user(question)
                    .call()
                    .content();

            long elapsedMs =
                    (System.nanoTime() - startTime) / 1_000_000;

            log.info(
                    "[AI-RESPONSE] request_id={}, latency_ms={}, answer_length={}",
                    requestId,
                    elapsedMs,
                    answer == null ? 0 : answer.length()
            );

            return answer;

        } catch (Exception e) {

            long elapsedMs =
                    (System.nanoTime() - startTime) / 1_000_000;

            log.error(
                    "[AI-ERROR] request_id={}, latency_ms={}, error={}",
                    requestId,
                    elapsedMs,
                    e.getMessage(),
                    e
            );

            throw e;
        }
    }
}