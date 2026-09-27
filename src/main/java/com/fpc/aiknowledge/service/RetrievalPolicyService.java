package com.fpc.aiknowledge.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.annotation.PostConstruct;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * 检索策略（自进化闭环的落地端）。
 *
 * <p>策略文件由 {@code evolution/auto_tune.py} 在标注验证集上扫参产生：
 * 阈值、候选数、精排数不是拍脑袋定的，而是评测集选出来的。应用启动时读取该文件，
 * 让"评测选出的参数"真正生效——否则调优结果只停留在报告里。
 *
 * <p>文件缺失、解析失败或取值越界时回落到内置默认值（阈值 0.60 / 召回 Top5 / 精排 Top3），
 * 并在启动日志里说明，绝不因为策略文件的问题导致服务起不来。
 */
@Service
public class RetrievalPolicyService {

    private static final Logger log =
            LoggerFactory.getLogger(RetrievalPolicyService.class);

    /** 默认拒答阈值：60 条标定子集（44 库内 + 16 库外）扫描得出，P=1.0、FAR=0。 */
    public static final double DEFAULT_THRESHOLD = 0.60;
    public static final int DEFAULT_TOP_K = 5;
    public static final int DEFAULT_RERANK_TOP_K = 3;

    @Value("${knowledge.policy.path:evaluation/selected_policy.json}")
    private String policyPath;

    private final ObjectMapper objectMapper = new ObjectMapper();

    private volatile Policy policy = Policy.defaults();

    /**
     * 生效中的检索策略。
     *
     * @param relevanceThreshold 拒答阈值
     * @param topK               混合检索候选数
     * @param rerankTopK         精排后进入上下文的片段数
     * @param method             策略来源方法名（如 hybrid+rerank）
     * @param selectedAt         策略产出时间（来自策略文件）
     * @param policyVersion      策略文件版本号
     * @param loadedFromFile     是否成功从策略文件加载（false = 内置默认值）
     * @param path               策略文件路径
     */
    public record Policy(
            double relevanceThreshold,
            int topK,
            int rerankTopK,
            String method,
            String selectedAt,
            int policyVersion,
            boolean loadedFromFile,
            String path) {

        public static Policy defaults() {
            return new Policy(
                    DEFAULT_THRESHOLD,
                    DEFAULT_TOP_K,
                    DEFAULT_RERANK_TOP_K,
                    "builtin-default",
                    "",
                    0,
                    false,
                    ""
            );
        }

        public Map<String, Object> toMap() {
            Map<String, Object> map = new LinkedHashMap<>();
            map.put("relevance_threshold", relevanceThreshold);
            map.put("top_k", topK);
            map.put("rerank_top_k", rerankTopK);
            map.put("method", method);
            map.put("selected_at", selectedAt);
            map.put("policy_version", policyVersion);
            map.put("loaded_from_file", loadedFromFile);
            map.put("path", path);
            return map;
        }
    }

    @PostConstruct
    public void load() {
        this.policy = readPolicy();
        Policy current = this.policy;

        if (current.loadedFromFile()) {
            log.info(
                    "检索策略已加载：阈值={} 候选Top{} 精排Top{} 来源={}（{}）",
                    current.relevanceThreshold(),
                    current.topK(),
                    current.rerankTopK(),
                    current.method(),
                    current.selectedAt()
            );
        } else {
            log.warn(
                    "未找到可用的策略文件（{}），使用内置默认值：阈值={} 候选Top{} 精排Top{}",
                    current.path(),
                    current.relevanceThreshold(),
                    current.topK(),
                    current.rerankTopK()
            );
        }
    }

    /** 供运维接口触发重载：重新跑完 auto_tune 后无需重启应用。 */
    public Policy reload() {
        load();
        return current();
    }

    public Policy current() {
        return policy;
    }

    private Policy readPolicy() {

        Path path = Path.of(policyPath);
        Policy fallback = Policy.defaults();

        if (!Files.isReadable(path)) {
            return new Policy(
                    fallback.relevanceThreshold(),
                    fallback.topK(),
                    fallback.rerankTopK(),
                    fallback.method(),
                    fallback.selectedAt(),
                    fallback.policyVersion(),
                    false,
                    path.toAbsolutePath().toString()
            );
        }

        try {
            JsonNode node = objectMapper.readTree(Files.readString(path));

            double threshold = node.hasNonNull("relevance_threshold")
                    ? node.get("relevance_threshold").asDouble()
                    : DEFAULT_THRESHOLD;

            int topK = node.hasNonNull("top_k")
                    ? node.get("top_k").asInt()
                    : DEFAULT_TOP_K;

            int rerankTopK = node.hasNonNull("rerank_top_k")
                    ? node.get("rerank_top_k").asInt()
                    : DEFAULT_RERANK_TOP_K;

            if (threshold <= 0 || threshold >= 1 || topK < 1 || rerankTopK < 1) {
                log.warn(
                        "策略文件取值越界（阈值={} topK={} rerankTopK={}），忽略该文件",
                        threshold,
                        topK,
                        rerankTopK
                );
                return new Policy(
                        fallback.relevanceThreshold(),
                        fallback.topK(),
                        fallback.rerankTopK(),
                        fallback.method(),
                        fallback.selectedAt(),
                        fallback.policyVersion(),
                        false,
                        path.toAbsolutePath().toString()
                );
            }

            return new Policy(
                    threshold,
                    topK,
                    rerankTopK,
                    node.path("method").asText("unknown"),
                    node.path("selected_at").asText(""),
                    node.path("policy_version").asInt(0),
                    true,
                    path.toAbsolutePath().toString()
            );

        } catch (Exception e) {
            log.warn("策略文件解析失败（{}）：{}", path, e.getMessage());
            return new Policy(
                    fallback.relevanceThreshold(),
                    fallback.topK(),
                    fallback.rerankTopK(),
                    fallback.method(),
                    fallback.selectedAt(),
                    fallback.policyVersion(),
                    false,
                    path.toAbsolutePath().toString()
            );
        }
    }
}
