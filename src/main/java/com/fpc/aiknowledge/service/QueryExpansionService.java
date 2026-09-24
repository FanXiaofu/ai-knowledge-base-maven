package com.fpc.aiknowledge.service;

import org.springframework.ai.chat.model.ChatModel;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

@Service
public class QueryExpansionService {

    private final ChatModel chatModel;

    public QueryExpansionService(ChatModel chatModel) {
        this.chatModel = chatModel;
    }

    /**
     * 将用户自然语言问题转换为多个适合知识库检索的 Query。
     *
     * 原始问题保留，扩展 Query 用于补充专业术语和不同表达方式。
     */
    public List<String> expand(String question) {

        if (question == null || question.isBlank()) {
            return List.of();
        }



        String prompt = """
                你是一个知识库检索 Query 改写器。

                你的任务不是回答问题，而是把用户问题改写成适合知识库检索的查询语句。

                要求：
                1. 保留用户问题的核心含义。
                2. 补充可能出现在知识库中的专业术语、核心概念或同义表达。
                3. 生成 2~3 个扩展查询。
                4. 每个查询必须简短。
                5. 优先使用中文。
                6. 可以保留 Spring、Bean、Redis、MySQL、JVM、API 等技术名词。
                7. 不要生成纯英文查询。
                8. 不要回答问题。
                9. 不要添加问题中没有依据的具体技术事实。
                10. 每行只输出一个查询，不要编号，不要解释。

                用户问题：
                %s
                """.formatted(question);

        String response = chatModel.call(prompt);

        if (response == null || response.isBlank()) {
            return List.of(question);
        }

        List<String> queries = new ArrayList<>();

        // 原始 Query 始终保留
        queries.add(question);

        Arrays.stream(response.split("\\R"))
                .map(String::trim)
                .map(line -> line.replaceFirst("^\\d+[.、)]\\s*", ""))
                .map(line -> line.replaceFirst("^[-*]\\s*", ""))
                .filter(line -> !line.isBlank())
                .filter(line -> !line.equals(question))
                .limit(3)
                .forEach(queries::add);

        return queries;
    }
}