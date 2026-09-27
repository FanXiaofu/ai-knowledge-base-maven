package com.fpc.aiknowledge.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.annotation.PostConstruct;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 自进化闭环的落库端：问答轨迹（qa_trace）与用户反馈（qa_feedback）。
 *
 * <p>为什么要落轨迹：badcase 归因需要知道"回答时到底检索到了什么、精排打了多少分、
 * 是否拒答"，只存一个问答文本没法定位失败层（检索没搜到 / 精排压错 / 阈值误伤 / 生成出错）。
 *
 * <p>写库失败不抛出：轨迹是旁路数据，不能因为它写不进去就让问答请求失败，
 * 但会记 WARN 日志，避免"静默丢数据"。
 */
@Service
public class EvolutionStore {

    private static final Logger log =
            LoggerFactory.getLogger(EvolutionStore.class);

    private final JdbcTemplate jdbcTemplate;

    private final ObjectMapper objectMapper = new ObjectMapper();

    public EvolutionStore(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @PostConstruct
    public void initSchema() {

        jdbcTemplate.execute("""
                CREATE TABLE IF NOT EXISTS qa_trace (
                    id BIGSERIAL PRIMARY KEY,
                    trace_id TEXT UNIQUE NOT NULL,
                    question TEXT NOT NULL,
                    refused BOOLEAN NOT NULL,
                    refuse_reason TEXT,
                    top1_score DOUBLE PRECISION,
                    threshold_used DOUBLE PRECISION,
                    policy_source TEXT,
                    hits JSONB NOT NULL DEFAULT '{}'::jsonb,
                    answer TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """);

        jdbcTemplate.execute("""
                CREATE INDEX IF NOT EXISTS idx_qa_trace_created
                ON qa_trace (created_at DESC)
                """);

        jdbcTemplate.execute("""
                CREATE TABLE IF NOT EXISTS qa_feedback (
                    id BIGSERIAL PRIMARY KEY,
                    trace_id TEXT NOT NULL,
                    rating TEXT NOT NULL,
                    expected_source TEXT,
                    expected_section TEXT,
                    comment TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """);

        jdbcTemplate.execute("""
                CREATE INDEX IF NOT EXISTS idx_qa_feedback_trace
                ON qa_feedback (trace_id)
                """);

        log.info("自进化闭环存储就绪：qa_trace / qa_feedback");
    }

    /**
     * 记录一次问答轨迹。
     *
     * @param traceId       轨迹 ID（返回给调用方，反馈时带回来）
     * @param question      原始问题
     * @param refused       是否拒答
     * @param refuseReason  拒答原因（无候选 / 低于阈值 / null）
     * @param top1Score     精排 Top-1 分数（无候选时为 null）
     * @param thresholdUsed 本次使用的拒答阈值
     * @param policySource  策略来源（策略文件方法名或 builtin-default）
     * @param retrieval     检索现场：{"candidates": [...], "reranked": [...]}，
     *                      归因时用它区分"召回没搜到"与"精排压错"
     * @param answer        最终回答（拒答时为拒答文案）
     */
    public boolean recordTrace(
            String traceId,
            String question,
            boolean refused,
            String refuseReason,
            Double top1Score,
            double thresholdUsed,
            String policySource,
            Map<String, Object> retrieval,
            String answer) {

        try {

            String retrievalJson = objectMapper.writeValueAsString(retrieval);

            jdbcTemplate.update(
                    """
                    INSERT INTO qa_trace (
                        trace_id, question, refused, refuse_reason,
                        top1_score, threshold_used, policy_source, hits, answer
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?::jsonb, ?)
                    ON CONFLICT (trace_id) DO NOTHING
                    """,
                    traceId,
                    question,
                    refused,
                    refuseReason,
                    top1Score,
                    thresholdUsed,
                    policySource,
                    retrievalJson,
                    answer
            );

            return true;

        } catch (Exception e) {

            log.warn("问答轨迹写入失败（trace_id={}）：{}", traceId, e.getMessage());
            return false;
        }
    }

    /**
     * 记录用户反馈（点赞/点踩，可带期望来源）。
     *
     * @return 反馈 ID
     */
    public long recordFeedback(
            String traceId,
            String rating,
            String expectedSource,
            String expectedSection,
            String comment) {

        Long id = jdbcTemplate.queryForObject(
                """
                INSERT INTO qa_feedback (
                    trace_id, rating, expected_source, expected_section, comment
                ) VALUES (?, ?, ?, ?, ?)
                RETURNING id
                """,
                Long.class,
                traceId,
                rating,
                expectedSource,
                expectedSection,
                comment
        );

        return id == null ? -1L : id;
    }

    /**
     * 导出最近若干条轨迹与反馈，供 evolution/evolve.py 做归因与评测集生长。
     */
    public Map<String, Object> export(int limit) {

        List<Map<String, Object>> traces = jdbcTemplate.queryForList(
                """
                SELECT trace_id, question, refused, refuse_reason, top1_score,
                       threshold_used, policy_source, hits::text AS hits, answer, created_at
                FROM qa_trace
                ORDER BY id DESC
                LIMIT ?
                """,
                limit
        );

        List<Map<String, Object>> feedback = jdbcTemplate.queryForList(
                """
                SELECT f.id, f.trace_id, f.rating, f.expected_source,
                       f.expected_section, f.comment, f.created_at
                FROM qa_feedback f
                ORDER BY f.id DESC
                LIMIT ?
                """,
                limit
        );

        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("traces", traces);
        payload.put("feedback", feedback);
        return payload;
    }

    /**
     * 闭环运行概况：轨迹数、拒答数、反馈数、待归因（有反馈的）题数。
     */
    public Map<String, Object> summary() {

        Map<String, Object> summary = new LinkedHashMap<>();

        summary.put(
                "traces",
                jdbcTemplate.queryForObject("SELECT count(*) FROM qa_trace", Long.class)
        );

        summary.put(
                "refused",
                jdbcTemplate.queryForObject(
                        "SELECT count(*) FROM qa_trace WHERE refused",
                        Long.class
                )
        );

        summary.put(
                "feedback",
                jdbcTemplate.queryForObject("SELECT count(*) FROM qa_feedback", Long.class)
        );

        summary.put(
                "feedback_down",
                jdbcTemplate.queryForObject(
                        "SELECT count(*) FROM qa_feedback WHERE rating = 'down'",
                        Long.class
                )
        );

        summary.put(
                "feedback_with_expected_source",
                jdbcTemplate.queryForObject(
                        "SELECT count(*) FROM qa_feedback WHERE expected_source IS NOT NULL",
                        Long.class
                )
        );

        return summary;
    }
}
