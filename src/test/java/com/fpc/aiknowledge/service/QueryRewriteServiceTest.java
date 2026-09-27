package com.fpc.aiknowledge.service;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * 改写结果清洗的测试。
 *
 * 模型输出的脏数据是这类改写最常见的翻车点：带上"改写后："、"我改写为…"、
 * 整段引号、换行解释。不清理就会把噪声带进检索查询，直接拉低召回。
 */
class QueryRewriteServiceTest {

    @Test
    void stripsLabelPrefix() {
        assertEquals("Redis 分布式锁的默认过期时间是多少？",
                QueryRewriteService.clean("改写后：Redis 分布式锁的默认过期时间是多少？"));
    }

    @Test
    void stripsQuotes() {
        assertEquals("Redis 的持久化方式有哪些",
                QueryRewriteService.clean("\"Redis 的持久化方式有哪些\""));
        assertEquals("Redis 的持久化方式有哪些",
                QueryRewriteService.clean("「Redis 的持久化方式有哪些」"));
    }

    @Test
    void keepsOnlyFirstLine() {
        assertEquals("Redis 分布式锁怎么实现",
                QueryRewriteService.clean("Redis 分布式锁怎么实现\n\n说明：我把\"它\"补全成了 Redis。"));
    }

    @Test
    void collapsesWhitespace() {
        assertEquals("Redis 缓存 击穿 与 雪崩",
                QueryRewriteService.clean("Redis   缓存\t击穿 与  雪崩"));
    }

    @Test
    void truncatesOverlongOutput() {
        String raw = "查询".repeat(500);
        String cleaned = QueryRewriteService.clean(raw);
        assertTrue(cleaned.length() <= 300, "超长输出多半是模型在解释，必须截断");
    }

    @Test
    void emptyAndBlankAreEmpty() {
        assertEquals("", QueryRewriteService.clean(null));
        assertEquals("", QueryRewriteService.clean("   "));
    }

    @Test
    void plainQuestionIsUnchanged() {
        String question = "Kubernetes 探针有哪几种";
        assertEquals(question, QueryRewriteService.clean(question));
    }
}
