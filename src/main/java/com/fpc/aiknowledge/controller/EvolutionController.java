package com.fpc.aiknowledge.controller;

import com.fpc.aiknowledge.service.EvolutionStore;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * 自进化闭环的接口面。
 *
 * <pre>
 * 用户反馈 → qa_feedback ─┐
 *                        ├─► evolution/evolve.py 归因 → 评测集生长 → evolution/regression.py 回归门禁
 * 问答轨迹 → qa_trace ────┘
 * </pre>
 *
 * 这里只负责"收数据、导出数据"；归因与用例生长放在 Python 侧，
 * 因为那部分要与评测脚本、标注验证集共用同一套口径。
 */
@RestController
@RequestMapping("/api")
public class EvolutionController {

    private static final String RATING_UP = "up";
    private static final String RATING_DOWN = "down";

    private final EvolutionStore evolutionStore;

    public EvolutionController(EvolutionStore evolutionStore) {
        this.evolutionStore = evolutionStore;
    }

    /**
     * 提交反馈。
     *
     * 请求体：{@code {"trace_id": "qa-...", "rating": "up|down",
     * "expected_source": "redis.md", "expected_section": "Redis 分布式锁", "comment": "..."}}
     *
     * expected_source 是可选但关键的字段：填了它，evolve.py 才能自动判断失败层
     * （召回没搜到 / 精排压错 / 阈值误伤），并把这条 badcase 转成带金标的评测用例。
     */
    @PostMapping("/feedback")
    public Map<String, Object> feedback(@RequestBody Map<String, Object> body) {

        String traceId = text(body.get("trace_id"));
        String rating = text(body.get("rating"));

        if (traceId.isBlank()) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "trace_id 不能为空");
        }

        if (!RATING_UP.equals(rating) && !RATING_DOWN.equals(rating)) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "rating 只能是 up 或 down");
        }

        long id = evolutionStore.recordFeedback(
                traceId,
                rating,
                text(body.get("expected_source")),
                text(body.get("expected_section")),
                text(body.get("comment"))
        );

        Map<String, Object> response = new LinkedHashMap<>();
        response.put("ok", true);
        response.put("feedback_id", id);
        response.put("trace_id", traceId);
        return response;
    }

    /**
     * 闭环运行概况（轨迹数、拒答数、反馈数、待归因数）。
     */
    @GetMapping("/evolution/summary")
    public Map<String, Object> summary() {
        return evolutionStore.summary();
    }

    /**
     * 导出最近若干条轨迹与反馈，供 evolution/evolve.py 归因。
     */
    @GetMapping("/evolution/export")
    public Map<String, Object> export(
            @RequestParam(defaultValue = "500") int limit) {

        return evolutionStore.export(Math.max(1, Math.min(limit, 5000)));
    }

    private String text(Object value) {
        return value == null ? "" : String.valueOf(value).trim();
    }
}
