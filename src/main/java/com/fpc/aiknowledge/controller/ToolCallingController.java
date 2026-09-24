package com.fpc.aiknowledge.controller;

import com.fpc.aiknowledge.service.ToolCallingService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/tool")
public class ToolCallingController {

    private final ToolCallingService toolCallingService;

    public ToolCallingController(ToolCallingService toolCallingService) {
        this.toolCallingService = toolCallingService;
    }

    @GetMapping("/chat")
    public String chat(@RequestParam String question) {
        return toolCallingService.chat(question);
    }
}
