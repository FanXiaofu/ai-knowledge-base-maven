package com.fpc.aiknowledge.service;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

import java.time.Duration;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 会话记忆：把同一会话的最近几轮问答存进 Redis，供指代消解使用。
 *
 * <p>为什么需要：RAG 主链路原本是单轮无状态的，"它的默认值是多少？"这类追问检索不到任何东西 ——
 * 指代对象只存在于上一轮对话里。把历史轮次带进查询改写，是"有记忆的问答"和"单轮问答"的分界。
 *
 * <p><b>fail-open 是硬要求</b>：记忆是增益而不是依赖。Redis 不可用（未启动/连不上）时
 * 全部操作降级为"无历史对话"，问答照常进行 —— 这个项目在引入 Redis 之前本来就能跑单轮。
 *
 * <p>窗口语义（{@link Window}）刻意做成不可变 + 纯函数：裁剪/渲染不碰 IO，
 * 可以用单元测试锁住"最多保留 N 轮、超出的从最旧开始丢"这类边界行为。
 */
@Service
public class ConversationMemoryService {

    private static final Logger log =
            LoggerFactory.getLogger(ConversationMemoryService.class);

    private static final DateTimeFormatter TIME_FMT =
            DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");

    /** 记忆窗口里的一轮问答（助手侧只留摘要与来源，避免把整篇回答塞回提示词）。 */
    public record Turn(String question, String answer, List<String> sources, String at) {

        public static Turn of(String question, String answer, List<String> sources) {
            return new Turn(question, answer, sources, LocalDateTime.now().format(TIME_FMT));
        }
    }

    /**
     * 会话窗口（不可变）。{@code turns} 按时间从旧到新排列。
     */
    public record Window(List<Turn> turns, int maxTurns, boolean redisAvailable) {

        public static Window empty(int maxTurns, boolean redisAvailable) {
            return new Window(List.of(), maxTurns, redisAvailable);
        }

        public boolean isEmpty() {
            return turns.isEmpty();
        }

        public int size() {
            return turns.size();
        }

        /** 追加一轮并裁剪到窗口上限（超出时丢最旧的）——纯函数，便于单测。 */
        public List<Turn> appended(Turn turn) {
            List<Turn> next = new ArrayList<>(turns);
            next.add(turn);
            if (maxTurns > 0 && next.size() > maxTurns) {
                next = new ArrayList<>(next.subList(next.size() - maxTurns, next.size()));
            }
            return List.copyOf(next);
        }

        /** 渲染成改写提示词里的对话历史文本。 */
        public String toPrompt() {
            if (turns.isEmpty()) {
                return "";
            }
            StringBuilder sb = new StringBuilder();
            for (Turn turn : turns) {
                sb.append("用户：").append(turn.question()).append("\n");
                sb.append("助手：").append(turn.answer() == null ? "" : turn.answer());
                if (turn.sources() != null && !turn.sources().isEmpty()) {
                    sb.append("（来源：").append(String.join("、", turn.sources())).append("）");
                }
                sb.append("\n");
            }
            return sb.toString().trim();
        }
    }

    private final StringRedisTemplate redisTemplate;

    /** 项目惯例：ObjectMapper 不是 Spring Bean，需要的地方自行创建。 */
    private final ObjectMapper objectMapper = new ObjectMapper();

    @Value("${knowledge.memory.enabled:true}")
    private boolean enabled;

    @Value("${knowledge.memory.max-turns:5}")
    private int maxTurns;

    @Value("${knowledge.memory.ttl-seconds:1800}")
    private long ttlSeconds;

    @Value("${knowledge.memory.key-prefix:kb:chat:}")
    private String keyPrefix;

    public ConversationMemoryService(StringRedisTemplate redisTemplate) {
        this.redisTemplate = redisTemplate;
    }

    public boolean isEnabled() {
        return enabled;
    }

    public int getMaxTurns() {
        return maxTurns;
    }

    private String key(String sessionId) {
        return keyPrefix + sessionId;
    }

    /**
     * 读取会话窗口。会话未指定、记忆关闭或 Redis 不可用时返回空窗口。
     */
    public Window load(String sessionId) {

        if (!enabled || sessionId == null || sessionId.isBlank()) {
            return Window.empty(maxTurns, true);
        }

        try {
            String raw = redisTemplate.opsForValue().get(key(sessionId));
            if (raw == null || raw.isBlank()) {
                return Window.empty(maxTurns, true);
            }

            List<Turn> turns = objectMapper.readValue(raw, new TypeReference<List<Turn>>() {
            });

            return new Window(List.copyOf(turns), maxTurns, true);

        } catch (Exception e) {
            // Redis 不可用：降级为无历史对话，问答继续
            log.warn("会话记忆读取失败（session={}），本次按无历史处理：{}", sessionId, e.getMessage());
            return Window.empty(maxTurns, false);
        }
    }

    /**
     * 追加一轮问答并刷新 TTL。失败只告警：记忆写不进去不该影响回答。
     */
    public boolean append(String sessionId, Turn turn) {

        if (!enabled || sessionId == null || sessionId.isBlank() || turn == null) {
            return false;
        }

        try {
            Window window = load(sessionId);
            List<Turn> next = window.appended(turn);
            String raw = objectMapper.writeValueAsString(next);

            redisTemplate.opsForValue().set(key(sessionId), raw, Duration.ofSeconds(ttlSeconds));
            return true;

        } catch (Exception e) {
            log.warn("会话记忆写入失败（session={}）：{}", sessionId, e.getMessage());
            return false;
        }
    }

    /**
     * 清空指定会话的记忆。
     */
    public boolean clear(String sessionId) {

        if (sessionId == null || sessionId.isBlank()) {
            return false;
        }

        try {
            return Boolean.TRUE.equals(redisTemplate.delete(key(sessionId)));
        } catch (Exception e) {
            log.warn("会话记忆清除失败（session={}）：{}", sessionId, e.getMessage());
            return false;
        }
    }

    /**
     * 会话概况（供运维接口查看记忆是否真的在工作）。
     */
    public Map<String, Object> describe(String sessionId) {

        Map<String, Object> info = new LinkedHashMap<>();
        Window window = load(sessionId);

        info.put("session_id", sessionId);
        info.put("memory_enabled", enabled);
        info.put("redis_available", window.redisAvailable());
        info.put("max_turns", maxTurns);
        info.put("ttl_seconds", ttlSeconds);
        info.put("turns", window.size());

        List<Map<String, Object>> preview = new ArrayList<>();
        for (Turn turn : window.turns()) {
            Map<String, Object> row = new LinkedHashMap<>();
            row.put("question", turn.question());
            row.put("sources", turn.sources());
            row.put("at", turn.at());
            preview.add(row);
        }
        info.put("history", preview);

        return info;
    }
}
