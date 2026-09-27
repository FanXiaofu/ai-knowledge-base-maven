package com.fpc.aiknowledge.controller;

import com.fpc.aiknowledge.service.ConversationMemoryService;
import com.fpc.aiknowledge.service.RagChatService;
import com.fpc.aiknowledge.service.RetrievalPolicyService;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * RAG 问答接口。
 *
 * 返回结构化 JSON 而不是纯文本：调用方需要 trace_id ——
 * 对回答不满意时用它在 POST /api/feedback 里反馈，这条反馈会进入
 * badcase 归因 → 评测集生长 → 回归门禁的自进化闭环。
 *
 * 带 sessionId 时启用会话记忆：追问里的"它/这个"会先被改写成可独立检索的问题，
 * 响应里的 retrieval_query 就是实际用于检索的那一条（用于验证改写是否生效）。
 */
@RestController
@RequestMapping("/api/chat")
public class RagChatController {

    private final RagChatService ragChatService;
    private final RetrievalPolicyService policyService;
    private final ConversationMemoryService conversationMemory;

    public RagChatController(
            RagChatService ragChatService,
            RetrievalPolicyService policyService,
            ConversationMemoryService conversationMemory) {

        this.ragChatService = ragChatService;
        this.policyService = policyService;
        this.conversationMemory = conversationMemory;
    }

    @GetMapping
    public Map<String, Object> chat(
            @RequestParam String question,
            @RequestParam(required = false) String sessionId) {

        try {

            Map<String, Object> body =
                    ragChatService.chat(question, sessionId).toMap();

            body.put("policy", policyService.current().toMap());

            return body;

        } catch (IllegalArgumentException e) {

            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    e.getMessage(),
                    e
            );

        } catch (Exception e) {

            throw new ResponseStatusException(
                    HttpStatus.INTERNAL_SERVER_ERROR,
                    "RAG问答失败：" + e.getMessage(),
                    e
            );
        }
    }

    /**
     * 查看某个会话的记忆概况（有几轮、最近问了什么、Redis 是否可用）。
     */
    @GetMapping("/session")
    public Map<String, Object> session(@RequestParam String sessionId) {
        return conversationMemory.describe(sessionId);
    }

    /**
     * 清空某个会话的记忆。
     */
    @DeleteMapping("/session")
    public Map<String, Object> clearSession(@RequestParam String sessionId) {

        Map<String, Object> body = new LinkedHashMap<>();
        body.put("session_id", sessionId);
        body.put("cleared", conversationMemory.clear(sessionId));
        return body;
    }

    /**
     * 当前生效的检索策略（阈值 / 候选数 / 精排数 / 来源与时间）。
     */
    @GetMapping("/policy")
    public Map<String, Object> policy() {

        Map<String, Object> body = new LinkedHashMap<>();
        body.put("policy", policyService.current().toMap());
        return body;
    }

    /**
     * 重新加载策略文件（auto_tune.py 重新扫参后无需重启应用）。
     */
    @PostMapping("/policy/reload")
    public Map<String, Object> reloadPolicy() {

        Map<String, Object> body = new LinkedHashMap<>();
        body.put("reloaded", true);
        body.put("policy", policyService.reload().toMap());
        return body;
    }
}
