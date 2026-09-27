package com.fpc.aiknowledge.service;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.model.ChatModel;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.util.List;

/**
 * 查询改写：把带指代/省略的追问补全成"能独立检索"的问题。
 *
 * <p>会话记忆本身不解决问题——记忆只是把历史轮次拿出来；真正让追问能检索到东西的是这一步：
 * "它的默认值是多少？" → "Redis 分布式锁的默认过期时间是多少？"
 *
 * <p>只在**有历史对话**时才调用模型（无历史时改写无从下手，白花一次调用）；
 * 改写失败/输出异常时原样返回原问题（fail-open），绝不因为改写而让问答失败。
 */
@Service
public class QueryRewriteService {

    private static final Logger log =
            LoggerFactory.getLogger(QueryRewriteService.class);

    /** 改写结果的长度上限：检索用的查询词不需要长文，超长多半是模型在解释而不是在改写。 */
    private static final int MAX_QUERY_CHARS = 300;

    /** 模型偶尔会带上这些前缀/包裹符号，统一剥掉。 */
    private static final List<String> LABEL_PREFIXES = List.of(
            "改写后的问题是：", "改写后的问题：", "改写后的检索式：", "改写后：", "改写：",
            "独立问题：", "检索问题：", "问题：", "答案："
    );

    private static final String SYSTEM_PROMPT = """
            你是一个检索查询改写器。

            任务：把用户的"最新问题"改写成一个**不依赖对话历史也能独立检索**的问题。

            规则：
            1. 把代词与省略的指代对象补全为具体名词（指代对象来自对话历史）；
            2. 保留原问题里的关键词与措辞，不要换同义词，不要扩写、不要解释；
            3. 不要回答问题，不要输出多个问题；
            4. 如果最新问题本身已经可以独立检索，原样输出；
            5. 只输出改写后的问题本身，不要引号、不要前缀、不要标点之外的任何内容。
            """;

    private final ChatClient chatClient;

    @Value("${knowledge.memory.rewrite-enabled:true}")
    private boolean enabled;

    public QueryRewriteService(ChatModel chatModel) {
        this.chatClient = ChatClient.builder(chatModel).build();
    }

    /**
     * 改写结果。
     *
     * @param original  用户原始问题
     * @param query     实际用于检索的问题（未改写时等于 original）
     * @param rewritten 是否发生了改写
     * @param reason    改写/未改写的原因（写进轨迹，便于评测与排障）
     */
    public record Rewrite(String original, String query, boolean rewritten, String reason) {
    }

    /**
     * 清洗模型输出：取首行、剥掉标签前缀与包裹引号、压缩空白、限长。
     *
     * <p>纯函数，单独可测——模型输出的脏数据是这类改写最常见的翻车点
     * （带上"改写后："、换行解释、整段引号），不清理就会污染检索查询。
     */
    public static String clean(String raw) {

        if (raw == null || raw.isBlank()) {
            return "";
        }

        String text = raw.strip();

        // 取第一行：小模型常在第一行给结果，后面跟解释
        int newline = text.indexOf('\n');
        if (newline > 0) {
            text = text.substring(0, newline).strip();
        }

        for (String prefix : LABEL_PREFIXES) {
            if (text.startsWith(prefix)) {
                text = text.substring(prefix.length()).strip();
                break;
            }
        }

        text = text.replaceAll("^[\"'“”「」『』]+", "")
                .replaceAll("[\"'“”「」『』]+$", "")
                .strip();

        text = text.replaceAll("\\s+", " ");

        if (text.length() > MAX_QUERY_CHARS) {
            text = text.substring(0, MAX_QUERY_CHARS).strip();
        }

        return text;
    }

    private Rewrite passthrough(String question, String reason) {
        return new Rewrite(question, question, false, reason);
    }

    /**
     * 有历史对话时做指代消解；否则原样返回。
     */
    public Rewrite rewrite(String question, ConversationMemoryService.Window window) {

        if (question == null || question.isBlank()) {
            throw new IllegalArgumentException("问题不能为空");
        }

        if (!enabled) {
            return passthrough(question, "改写未启用");
        }

        if (window == null || window.isEmpty()) {
            return passthrough(question, "无历史对话");
        }

        String prompt = """
                对话历史（从旧到新，共 %d 轮）：
                %s

                最新问题：%s
                """.formatted(window.size(), window.toPrompt(), question);

        try {

            String raw = chatClient.prompt()
                    .system(SYSTEM_PROMPT)
                    .user(prompt)
                    .call()
                    .content();

            String rewritten = clean(raw);

            if (rewritten.isBlank()) {
                return passthrough(question, "改写结果为空");
            }

            if (rewritten.equals(question.strip())) {
                return passthrough(question, "本问题已可独立检索");
            }

            return new Rewrite(question, rewritten, true, "指代消解");

        } catch (Exception e) {

            log.warn("查询改写失败，按原问题检索：{}", e.getMessage());
            return passthrough(question, "改写失败：" + e.getMessage());
        }
    }
}
