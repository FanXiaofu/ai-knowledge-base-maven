package com.fpc.aiknowledge.controller;

import com.fpc.aiknowledge.service.AiChatService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AiChatController {

    private final AiChatService aiChatService;

    public AiChatController(AiChatService aiChatService) {
        this.aiChatService = aiChatService;
    }

    @GetMapping("/api/ai/chat")
    public String chat(@RequestParam String message) {
        return aiChatService.chat(message);
    }
}