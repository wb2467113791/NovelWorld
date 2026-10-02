package org.novelworld.world;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.ObjectMapper;

import static org.junit.jupiter.api.Assertions.*;

class ConversationPersistenceTest {
    final ObjectMapper mapper = new ObjectMapper();
    final org.springframework.jdbc.core.JdbcTemplate jdbc;
    final WorldStore store;
    final WorldMcpTools tools;
    final String worldId;
    final String otherId;

    ConversationPersistenceTest() {
        var source = new org.h2.jdbcx.JdbcDataSource();
        source.setURL("jdbc:h2:mem:conversation-" + UUID.randomUUID() + ";DB_CLOSE_DELAY=-1");
        jdbc = new org.springframework.jdbc.core.JdbcTemplate(source);
        jdbc.execute("CREATE TABLE world_saves (world_id VARCHAR(64) PRIMARY KEY, snapshot CLOB NOT NULL, revision BIGINT NOT NULL)");
        store = new WorldStore(jdbc, mapper);
        var templates = new WorldTemplateService(store, mapper);
        worldId = templates.createWorld(templates.defaultTemplate());
        otherId = templates.createWorld(templates.defaultTemplate());
        tools = new WorldMcpTools(store, new WorldRules(), mapper);
        tools.executeWorldTool(worldId, "move_character", "{\"character\":\"林默\",\"location\":\"晚风客栈\"}", "林默");
    }

    @SuppressWarnings("unchecked")
    Map<String, Object> talk(String speaker, String listener, String message) {
        tools.executeWorldTool(worldId, "talk", mapper.writeValueAsString(Map.of("speaker", speaker,
                "listener", listener, "message", message)), speaker);
        var events = (List<Map<String, Object>>) store.load(worldId).get("events");
        return events.get(events.size() - 1);
    }

    Map<String, Object> session(List<Map<String, Object>> events) {
        var messages = new ArrayList<Object>();
        for (int index = 0; index < events.size(); index++) {
            var event = events.get(index);
            messages.add(new HashMap<>(Map.of("speaker", event.get("actor"), "content", ((Map<?, ?>) event.get("payload")).get("message"),
                    "tick", 10 + index, "event_id", event.get("id"))));
        }
        return new HashMap<>(Map.of("id", "session-1", "participants", List.of("林默", "苏晚"), "location", "晚风客栈",
                "status", "active", "messages", messages, "started_tick", 10, "last_activity_tick", 9 + events.size(),
                "next_speaker", events.get(events.size() - 1).get("target")));
    }

    Map<String, Object> payload(String id, List<?> conversations) {
        return new HashMap<>(Map.of("characters", ObjectPersistenceTest.npcs(store.load(id).get("characters")),
                "scheduler", Map.of("tick_count", 12, "pending", List.of()), "active_conversations", conversations));
    }

    @Test void realTalkMessagesPersistAcrossStoreReconnectAndStayWorldIsolated() {
        var first = talk("林默", "苏晚", "你最近好吗？");
        var second = talk("苏晚", "林默", "今天很平静。");
        var conversation = session(List.of(first, second));
        var before = store.load(worldId);
        tools.saveAgentState(worldId, mapper.writeValueAsString(payload(worldId, List.of(conversation))));
        var saved = new WorldStore(jdbc, mapper).load(worldId);
        assertEquals(List.of(conversation), saved.get("active_conversations"));
        assertEquals(before.get("events"), saved.get("events"));
        assertEquals(before.get("time"), saved.get("time"));
        assertEquals(List.of("林默", "苏晚"), first.get("perceived_by"));
        assertFalse(store.load(otherId).containsKey("active_conversations"));
    }

    @Test void runtimeCannotFabricateMessageOrImportAnotherWorldTalk() {
        var event = talk("林默", "苏晚", "真实发言");
        var conversation = session(List.of(event));
        @SuppressWarnings("unchecked")
        var message = (Map<String, Object>) ((List<?>) conversation.get("messages")).get(0);
        message.put("content", "模型声称的虚假发言");
        var before = store.load(worldId);
        assertThrows(IllegalArgumentException.class,
                () -> tools.saveAgentState(worldId, mapper.writeValueAsString(payload(worldId, List.of(conversation)))));
        assertEquals(before, store.load(worldId));
        message.put("content", "真实发言");
        var otherBefore = store.load(otherId);
        assertThrows(IllegalArgumentException.class,
                () -> tools.saveAgentState(otherId, mapper.writeValueAsString(payload(otherId, List.of(conversation)))));
        assertEquals(otherBefore, store.load(otherId));
    }

    @Test void invalidTurnDuplicateSessionAndUnboundedMessagesAreRejectedAtomically() {
        var event = talk("林默", "苏晚", "你好");
        var conversation = session(List.of(event));
        var before = store.load(worldId);
        conversation.put("next_speaker", "林默");
        assertThrows(IllegalArgumentException.class,
                () -> tools.saveAgentState(worldId, mapper.writeValueAsString(payload(worldId, List.of(conversation)))));
        conversation.put("next_speaker", "苏晚");
        var duplicate = new HashMap<>(conversation);
        duplicate.put("id", "session-2");
        assertThrows(IllegalArgumentException.class,
                () -> tools.saveAgentState(worldId, mapper.writeValueAsString(payload(worldId, List.of(conversation, duplicate)))));
        var many = new ArrayList<Object>((List<?>) conversation.get("messages"));
        while (many.size() <= 12) many.add(many.get(0));
        conversation.put("messages", many);
        assertThrows(IllegalArgumentException.class,
                () -> tools.saveAgentState(worldId, mapper.writeValueAsString(payload(worldId, List.of(conversation)))));
        assertEquals(before, store.load(worldId));
    }

    @Test void endingRemovesActiveRuntimeButKeepsAuthoritativeTalkEvents() {
        var event = talk("林默", "苏晚", "再见");
        tools.saveAgentState(worldId, mapper.writeValueAsString(payload(worldId, List.of(session(List.of(event))))));
        var beforeEvents = store.load(worldId).get("events");
        tools.saveAgentState(worldId, mapper.writeValueAsString(payload(worldId, List.of())));
        assertEquals(List.of(), new WorldStore(jdbc, mapper).load(worldId).get("active_conversations"));
        assertEquals(beforeEvents, store.load(worldId).get("events"));
    }

    @Test void talkStillRequiresCorrectActorAndSameLocationBeforeAnyEvent() {
        var before = store.load(worldId);
        assertThrows(IllegalArgumentException.class, () -> tools.executeWorldTool(worldId, "talk",
                "{\"speaker\":\"林默\",\"listener\":\"苏晚\",\"message\":\"你好\"}", "苏晚"));
        assertThrows(IllegalArgumentException.class, () -> tools.executeWorldTool(worldId, "talk",
                "{\"speaker\":\"林默\",\"listener\":\"赵无极\",\"message\":\"你好\"}", "林默"));
        assertEquals(before, store.load(worldId));
        assertThrows(IllegalArgumentException.class, () -> tools.executeWorldTool(worldId, "talk",
                "{\"speaker\":\"林默\",\"listener\":\"林默\",\"message\":\"你好\"}", "林默"));
    }
}
