package org.novelworld.world;

import static org.junit.jupiter.api.Assertions.*;
import java.lang.reflect.InvocationTargetException;
import java.util.*;
import org.junit.jupiter.api.*;
import org.springframework.boot.SpringApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.ai.mcp.annotation.McpTool;
import tools.jackson.databind.ObjectMapper;

/** 最小H2集成验收：真实Spring事务、既有规则、持久回执、旧存档与视角投影。 */
public class NativeToolsTest {
    static ConfigurableApplicationContext context;
    static WorldStore store;
    static WorldMcpTools tools;
    static WorldTemplateService templates;
    static ObjectMapper mapper;
    public static void main(String[] args) {
        var demo = SpringApplication.run(WorldServiceApplication.class, "--server.port=18080",
                "--spring.datasource.url=jdbc:h2:mem:mcpdemo;MODE=MySQL;DB_CLOSE_DELAY=-1",
                "--spring.datasource.username=sa", "--spring.datasource.password=",
                "--novelworld.web.password=", "--novelworld.agent.url=http://127.0.0.1:18001");
        demo.getBean(JdbcTemplate.class).execute(
                "ALTER TABLE action_executions ADD CONSTRAINT reject_demo_request CHECK(request_id <> 'fail-storage')");
    }
    @BeforeAll static void start() {
        context = SpringApplication.run(WorldServiceApplication.class, "--server.port=0",
                "--spring.datasource.url=jdbc:h2:mem:nativetests;MODE=MySQL;DB_CLOSE_DELAY=-1",
                "--spring.datasource.username=sa", "--spring.datasource.password=", "--novelworld.web.password=");
        store = context.getBean(WorldStore.class); tools = context.getBean(WorldMcpTools.class);
        templates = context.getBean(WorldTemplateService.class); mapper = context.getBean(ObjectMapper.class);
    }
    @AfterAll static void stop() { context.close(); }
    String world() {
        var template = templates.defaultTemplate();
        WorldRules.map(template.get("characters")).values().forEach(raw -> WorldRules.map(raw).put("location", "晚风茶馆"));
        return templates.createWorld(template);
    }
    Map<String, Object> cognition(Map<String, Object> w, String actor) {
        var person = WorldRules.actor(w, actor);
        var mind = new LinkedHashMap<String, Object>();
        mind.put("goal", "生活"); mind.put("intention", "下一步"); mind.put("plan", new ArrayList<>());
        mind.put("reflection", ""); mind.put("relationship_notes", new LinkedHashMap<>());
        mind.put("last_decision", w.get("minute")); mind.put("next_decision", ((Number) w.get("minute")).intValue() + 5);
        mind.put("event_cursor", WorldRules.list(w.get("events")).size());
        mind.put("reflection_cursor", 0);
        return Map.of("mind", mind, "memories", person.get("memories"));
    }
    @SuppressWarnings("unchecked") Map<String,Object> invoke(String action, String id, String actor, String request,
                                                               Map<String,Object> w, Map<String,Object> args) {
        var input = new LinkedHashMap<String,Object>(args);
        input.put("worldId", id); input.put("actor", actor); input.put("requestId", request);
        input.put("expectedRevision", ((Number) w.get("revision")).longValue()); input.put("reason", "验收动机");
        input.put("cognitionJson", mapper.writeValueAsString(cognition(w, actor)));
        for (var method : WorldMcpTools.class.getMethods()) {
            var annotation = method.getAnnotation(McpTool.class);
            if (annotation != null && action.equals(annotation.name())) {
                Object[] values = Arrays.stream(method.getParameters()).map(p -> input.get(p.getName())).toArray();
                try {
                    Map<String,Object> result = mapper.readValue((String) method.invoke(tools, values), Map.class);
                    if ("rejected".equals(result.get("status"))) throw new IllegalArgumentException((String) result.get("error"));
                    return result;
                }
                catch (InvocationTargetException e) { throw (RuntimeException) e.getCause(); }
                catch (ReflectiveOperationException e) { throw new RuntimeException(e); }
            }
        }
        throw new AssertionError("缺少工具 " + action);
    }
    Map<String,Object> act(String action, String id, String actor, Map<String,Object> args) {
        return invoke(action, id, actor, WorldRules.id(), store.load(id), args);
    }
    @Test void nineToolsKeepConversationAndActivityRules() {
        String id = world(); var before = store.load(id);
        assertThrows(IllegalArgumentException.class, () -> act("say", id, "苏晚", Map.of("message", "越过会话")));
        assertEquals(before, store.load(id));
        act("invite", id, "苏晚", Map.of("target", "许宁", "message", "聊一会"));
        String invitation = (String) WorldRules.map(WorldRules.list(store.load(id).get("invitations")).get(0)).get("id");
        act("respond_invitation", id, "许宁", Map.of("invitation_id", invitation, "accept", true));
        assertThrows(IllegalArgumentException.class, () -> act("say", id, "苏晚", Map.of("message", "抢先")));
        act("say", id, "许宁", Map.of("message", "愿意，今天有什么安排？"));
        act("say", id, "苏晚", Map.of("message", "想留一点时间读书。"));
        var session = WorldRules.map(WorldRules.list(store.load(id).get("conversations")).get(0));
        assertEquals(2, WorldRules.list(session.get("messages")).size()); assertEquals("许宁", session.get("next_speaker"));
        act("leave_conversation", id, "苏晚", Map.of());
        assertTrue(WorldRules.list(store.load(id).get("conversations")).isEmpty());
        var w = store.load(id);
        String object = WorldRules.map(w.get("objects")).entrySet().stream()
                .filter(e -> "晚风茶馆".equals(WorldRules.map(e.getValue()).get("location"))).findFirst().orElseThrow().getKey();
        act("inspect", id, "苏晚", Map.of("object_id", object));
        String activity = WorldRules.map(w.get("activities")).entrySet().stream().filter(e -> {
            var a = WorldRules.map(e.getValue()); var roles = WorldRules.list(a.get("roles"));
            return WorldRules.list(a.get("locations")).contains("晚风茶馆") && (roles.isEmpty() || roles.contains("茶馆经营者"));
        }).findFirst().orElseThrow().getKey();
        act("start_activity", id, "苏晚", Map.of("activity_id", activity));
        assertThrows(IllegalArgumentException.class, () -> act("move", id, "苏晚", Map.of("location", "青石街")));
        act("stop_activity", id, "苏晚", Map.of());
        act("move", id, "苏晚", Map.of("location", "青石街")); act("wait", id, "苏晚", Map.of());
        tools.advanceWorld(id, 0); assertEquals(485, store.load(id).get("minute"));
        tools.advanceWorld(id, 0); assertEquals(485, store.load(id).get("minute"));
        tools.advanceWorld(id, 1); assertNull(WorldRules.actor(store.load(id), "苏晚").get("activity"));
        var p = WorldRules.actor(store.load(id), "苏晚");
        assertFalse(WorldRules.list(p.get("memories")).isEmpty()); assertEquals(480, WorldRules.map(p.get("mind")).get("last_decision"));
        assertFalse(store.load(id).containsKey("decisions"));
        var observe = WorldWebController.view(store.load(id), Map.of(), false);
        assertFalse(WorldRules.list(observe.get("decisions")).isEmpty());
        tools.joinPlayer(id, "旅人", "青石街");
        var play = WorldWebController.view(store.load(id), Map.of(), true);
        assertTrue(WorldRules.list(play.get("decisions")).isEmpty());
        for (Object raw : WorldRules.list(play.get("events"))) assertFalse(WorldRules.map(raw).containsKey("action_trace"));
        for (Object raw : WorldRules.map(play.get("characters")).values()) assertFalse(WorldRules.map(raw).containsKey("secrets"));
    }
    @Test void receiptsSurviveHistoryWindowAndRollbackWithWorld() {
        String id = world(); var before = store.load(id); String object = "tea_notice";
        object = WorldRules.map(before.get("objects")).entrySet().stream()
                .filter(e -> "晚风茶馆".equals(WorldRules.map(e.getValue()).get("location"))).findFirst().orElseThrow().getKey();
        final var args = Map.<String,Object>of("object_id", object);
        var first = invoke("inspect", id, "苏晚", "first-request", before, args);
        for (int i=0; i<121; i++) act("inspect", id, "苏晚", args);
        var latest = store.load(id);
        var replay = invoke("inspect", id, "苏晚", "first-request", before, args);
        assertEquals(first.get("execution"), replay.get("execution")); assertEquals(latest, store.load(id));
        assertThrows(IllegalArgumentException.class, () -> invoke("inspect", id, "苏晚", "first-request", latest, args));
        var jdbc = context.getBean(JdbcTemplate.class);
        jdbc.execute("ALTER TABLE action_executions ADD CONSTRAINT reject_test_request CHECK(request_id <> 'fail-storage')");
        assertThrows(RuntimeException.class, () -> invoke("inspect", id, "苏晚", "fail-storage", latest, args));
        assertEquals(latest, store.load(id)); assertNull(store.execution(id, "fail-storage"));
        jdbc.execute("ALTER TABLE action_executions DROP CONSTRAINT reject_test_request");
    }
    @Test void legacyDecisionMigratesAtomically() {
        String id = world(); var w = store.load(id);
        var events = new WorldRules().apply(w, "苏晚", "wait", Map.of());
        var trace = Map.<String,Object>of("id", "legacy", "actor", "苏晚", "action", "wait", "reason", "旧动机",
                "event_ids", List.of(WorldRules.map(events.get(0)).get("id")));
        w.put("decisions", new ArrayList<>(List.of(trace))); store.update(id, w);
        var migrated = store.load(id);
        assertFalse(migrated.containsKey("decisions")); assertNotNull(store.execution(id, "legacy"));
        assertEquals("旧动机", WorldRules.map(WorldRules.map(WorldRules.list(migrated.get("events")).get(0)).get("action_trace")).get("reason"));
        assertEquals(mapper.writeValueAsString(migrated), mapper.writeValueAsString(store.load(id)));
        assertEquals("committed", mapper.readValue(tools.getExecution(id, "苏晚", "legacy"), Map.class).get("status"));
    }
    @Test void conversationStillClosesAtTwelveAndAllowsNextActions() {
        String id = world();
        act("invite", id, "苏晚", Map.of("target", "许宁", "message", "聊聊读书"));
        String invitation = (String) WorldRules.map(WorldRules.list(store.load(id).get("invitations")).get(0)).get("id");
        act("respond_invitation", id, "许宁", Map.of("invitation_id", invitation, "accept", true));
        for (int i = 0; i < 12; i++) {
            assertEquals(i, WorldRules.list(WorldRules.map(WorldRules.list(store.load(id).get("conversations")).get(0)).get("messages")).size());
            act("say", id, i % 2 == 0 ? "许宁" : "苏晚", Map.of("message", i == 11 ? "那今天先聊到这里，下次见。" : "分享读书感受。"));
        }
        var w = store.load(id); assertTrue(WorldRules.list(w.get("conversations")).isEmpty());
        var ended = WorldRules.map(WorldRules.list(w.get("events")).get(WorldRules.list(w.get("events")).size() - 1));
        assertEquals("conversation_ended", ended.get("type"));
        assertEquals("本次交谈告一段落", WorldRules.map(ended.get("payload")).get("reason"));
        var memories = WorldRules.list(WorldRules.actor(w, "苏晚").get("memories"));
        assertTrue(memories.stream().map(WorldRules::map).anyMatch(m -> WorldRules.list(m.get("source_event_ids")).contains(ended.get("id"))));
        tools.advanceWorld(id, 0);
        act("wait", id, "苏晚", Map.of()); act("wait", id, "许宁", Map.of());
        assertNotNull(WorldRules.actor(store.load(id), "苏晚").get("activity"));
        assertNotNull(WorldRules.actor(store.load(id), "许宁").get("activity"));
    }
}
