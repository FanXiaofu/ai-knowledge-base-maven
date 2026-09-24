package com.fpc.aiknowledge.controller;

import com.fpc.aiknowledge.service.RagChatService;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/chat")
public class RagChatController {

    private final RagChatService ragChatService;

    public RagChatController(RagChatService ragChatService) {
        this.ragChatService = ragChatService;
    }

    @GetMapping
    public String chat(@RequestParam String question) {
        try {
            return ragChatService.chat(question);
        } catch (Exception e) {
            throw new RuntimeException("RAG问答失败", e);
        }
    }
}