package com.fpc.aiknowledge.service;

import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * 会话窗口的纯逻辑测试：裁剪、渲染、空窗口语义。
 *
 * 不依赖 Spring 上下文与 Redis —— 窗口是不可变值对象，边界行为（保留最新 N 轮）
 * 必须能被测试锁住，否则"记忆无限增长"这类问题只会在长会话里慢慢暴露。
 */
class ConversationMemoryServiceTest {

    private static ConversationMemoryService.Turn turn(String q, String a, String... sources) {
        return new ConversationMemoryService.Turn(q, a, List.of(sources), "2026-09-25 10:00:00");
    }

    @Test
    void emptyWindowIsEmpty() {
        ConversationMemoryService.Window window = ConversationMemoryService.Window.empty(5, true);
        assertTrue(window.isEmpty());
        assertEquals(0, window.size());
    }

    @Test
    void appendedKeepsInsertionOrder() {
        ConversationMemoryService.Window window = ConversationMemoryService.Window.empty(5, true);

        List<ConversationMemoryService.Turn> turns = window.appended(turn("问题一", "答一"));
        turns = new ConversationMemoryService.Window(turns, 5, true).appended(turn("问题二", "答二"));

        assertEquals(2, turns.size());
        assertEquals("问题一", turns.get(0).question());
        assertEquals("问题二", turns.get(1).question());
    }

    @Test
    void appendedTrimsOldestWhenOverLimit() {
        ConversationMemoryService.Window window = ConversationMemoryService.Window.empty(2, true);

        List<ConversationMemoryService.Turn> turns = List.of();
        for (int i = 1; i <= 4; i++) {
            window = new ConversationMemoryService.Window(turns, 2, true);
            turns = window.appended(turn("问题" + i, "答" + i));
        }

        assertEquals(2, turns.size());
        assertEquals("问题3", turns.get(0).question(), "超限时应丢最旧的，保留最新 2 轮");
        assertEquals("问题4", turns.get(1).question());
    }

    @Test
    void toPromptRendersHistoryWithSources() {
        List<ConversationMemoryService.Turn> turns = ConversationMemoryService.Window
                .empty(5, true)
                .appended(turn("Redis 分布式锁怎么实现", "用 SET NX EX 实现", "redis.md"));

        String prompt = new ConversationMemoryService.Window(turns, 5, true).toPrompt();

        assertTrue(prompt.contains("用户：Redis 分布式锁怎么实现"));
        assertTrue(prompt.contains("助手：用 SET NX EX 实现"));
        assertTrue(prompt.contains("来源：redis.md"));
    }

    @Test
    void toPromptOnEmptyWindowIsBlank() {
        assertEquals("", ConversationMemoryService.Window.empty(5, true).toPrompt());
    }

    @Test
    void windowReportsRedisAvailability() {
        assertFalse(ConversationMemoryService.Window.empty(5, false).redisAvailable(),
                "Redis 不可用时窗口应显式标记，便于排障时区分'没记忆'和'没连上'");
    }
}
