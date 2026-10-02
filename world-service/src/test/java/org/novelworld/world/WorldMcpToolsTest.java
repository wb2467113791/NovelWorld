package org.novelworld.world;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Collections;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.ObjectMapper;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class WorldMcpToolsTest {
    @Test void reportedBeliefsPersistOnlyWithVisibleRealSourcesAndNeverChangeObjects() {
        var fixture = new ObjectPersistenceTest(); fixture.move();
        var before = fixture.store.load(fixture.id).get("objects");
        fixture.act("talk", Map.of("speaker", "玩家", "listener", "林默", "message", "钥匙在县衙"), "玩家");
        var world = fixture.store.load(fixture.id);
        var events = WorldObjects.list(world.get("events"));
        var source = WorldObjects.map(events.get(events.size() - 1));
        var report = new HashMap<String, Object>(Map.of("id", "report", "owner", "林默", "content", "钥匙在县衙",
                "source_type", "report", "source_actor", "玩家", "source_event_id", source.get("id"),
                "confidence", 0.5, "status", "active", "order", events.size() - 1, "evidence_event_ids", List.of(source.get("id"))));
        var characters = ObjectPersistenceTest.npcs(world.get("characters"));
        var lin = WorldObjects.map(characters.get("林默"));
        lin.put("belief_memory", Map.of("entries", List.of(report)));
        var payload = Map.of("characters", characters, "scheduler", world.get("scheduler"));
        fixture.tools.saveAgentState(fixture.id, fixture.mapper.writeValueAsString(payload));
        var saved = new WorldStore(fixture.jdbc, fixture.mapper).load(fixture.id);
        assertEquals(lin.get("belief_memory"), WorldObjects.map(WorldObjects.map(saved.get("characters")).get("林默")).get("belief_memory"));
        assertEquals(before, saved.get("objects"));
        assertTrue(WorldObjects.list(WorldObjects.map(lin.get("semantic_memory")).get("facts")).isEmpty());
        assertFalse(WorldActors.player(saved).containsKey("belief_memory"));
        assertFalse(WorldObjects.map(WorldObjects.map(fixture.store.load(fixture.otherId).get("characters")).get("林默")).containsKey("belief_memory"));
        for (var forged : List.of(Map.of("source_actor", "苏晚"), Map.of("source_event_id", "missing"),
                Map.of("confidence", 1.0), Map.of("status", "verified"), Map.of("owner", "赵无极"))) {
            var invalid = new HashMap<String, Object>(report); invalid.putAll(forged);
            lin.put("belief_memory", Map.of("entries", List.of(invalid)));
            assertThrows(IllegalArgumentException.class, () -> fixture.tools.saveAgentState(fixture.id, fixture.mapper.writeValueAsString(payload)));
            assertEquals(saved, fixture.store.load(fixture.id));
        }
        lin.put("belief_memory", Map.of("entries", Collections.nCopies(51, report)));
        assertThrows(IllegalArgumentException.class, () -> fixture.tools.saveAgentState(fixture.id, fixture.mapper.writeValueAsString(payload)));
        lin.remove("belief_memory");
        var zhao = WorldObjects.map(characters.get("赵无极"));
        var invisible = new HashMap<>(report); invisible.put("owner", "赵无极");
        zhao.put("belief_memory", Map.of("entries", List.of(invisible)));
        assertThrows(IllegalArgumentException.class, () -> fixture.tools.saveAgentState(fixture.id, fixture.mapper.writeValueAsString(payload)));
        zhao.remove("belief_memory");
        fixture.tools.saveAgentState(fixture.id, fixture.mapper.writeValueAsString(payload)); // 旧客户端不能清空认知。
        assertEquals(Map.of("entries", List.of(report)), WorldObjects.map(WorldObjects.map(fixture.store.load(fixture.id).get("characters")).get("林默")).get("belief_memory"));
    }
    @Test
    @SuppressWarnings("unchecked")
    void cognitionPersistsInExistingSnapshotsWithoutOverwritingBusinessState() {
        var source = new org.h2.jdbcx.JdbcDataSource();
        source.setURL("jdbc:h2:mem:agent-runtime;DB_CLOSE_DELAY=-1");
        var jdbc = new org.springframework.jdbc.core.JdbcTemplate(source);
        jdbc.execute("CREATE TABLE world_saves (world_id VARCHAR(64) PRIMARY KEY, snapshot CLOB NOT NULL, revision BIGINT NOT NULL)");
        var mapper = new ObjectMapper();
        var store = new WorldStore(jdbc, mapper);
        var templates = new WorldTemplateService(store, mapper);
        String firstId = templates.createWorld(templates.defaultTemplate());
        String secondId = templates.createWorld(templates.defaultTemplate());
        var tools = new WorldMcpTools(store, new WorldRules(), mapper);
        var before = store.load(firstId);
        var characters = (Map<String, Object>) before.get("characters");
        var payloadCharacters = new HashMap<String, Object>();
        for (var entry : characters.entrySet()) {
            var person = (Map<String, Object>) entry.getValue();
            if (!WorldActors.isNpc(person)) continue;
            payloadCharacters.put(entry.getKey(), new HashMap<>(Map.of(
                    "memory", person.get("memory"), "semantic_memory", person.get("semantic_memory"))));
        }
        var linPayload = (Map<String, Object>) payloadCharacters.get("林默");
        var runtime = Map.of("active_goal", "找到失踪者的下落", "current_intention", "核对线索",
                "current_plan", "根据新信息调整调查方向", "busy_until", 300,
                "agenda", List.of(Map.of("id", "visit", "character", "林默", "due_tick", 310,
                        "intention", "继续调查", "status", "pending")));
        linPayload.put("runtime_state", runtime);
        linPayload.put("location", "晚风客栈");
        linPayload.put("energy", 0);
        var payload = new HashMap<String, Object>();
        payload.put("characters", payloadCharacters);
        payload.put("scheduler", Map.of("tick_count", 7));
        payload.put("events", List.of());
        payload.put("time", "23:59");
        tools.saveAgentState(firstId, mapper.writeValueAsString(payload));

        // 新建 Store 模拟重新连接，验证数据库快照而非进程内缓存。
        var reconnected = new WorldStore(jdbc, mapper);
        var saved = reconnected.load(firstId);
        var lin = (Map<String, Object>) ((Map<?, ?>) saved.get("characters")).get("林默");
        assertEquals(runtime, lin.get("runtime_state"));
        assertEquals("县衙", lin.get("location"));
        assertEquals(90, lin.get("energy"));
        assertEquals("08:00", saved.get("time"));
        assertEquals(before.get("events"), saved.get("events"));
        assertEquals(Map.of("tick_count", 7), saved.get("scheduler"));
        assertFalse(((Map<?, ?>) ((Map<?, ?>) reconnected.load(secondId).get("characters"))
                .get("林默")).containsKey("runtime_state"));

        // 未携带认知的旧客户端不能清空已保存认知。
        linPayload.remove("runtime_state");
        tools.saveAgentState(firstId, mapper.writeValueAsString(payload));
        assertEquals(runtime, ((Map<?, ?>) ((Map<?, ?>) store.load(firstId).get("characters"))
                .get("林默")).get("runtime_state"));

        // save_agent_state 是内部 Runtime 的完整持久化通道，不是模型 cognition 更新接口。
        // 程序维护的调度状态仍需无损保存，不能随模型字段白名单一起被删除。
        for (String status : List.of("completed", "cancelled")) {
            var systemRuntime = new HashMap<String, Object>(runtime);
            systemRuntime.put("agenda", List.of(Map.of("id", "visit", "character", "林默", "due_tick", 310,
                    "intention", "继续调查", "status", status)));
            systemRuntime.put("busy_until", null);
            linPayload.put("runtime_state", systemRuntime);
            tools.saveAgentState(firstId, mapper.writeValueAsString(payload));
            assertEquals(systemRuntime, ((Map<?, ?>) ((Map<?, ?>) reconnected.load(firstId).get("characters"))
                    .get("林默")).get("runtime_state"));
            assertFalse(((Map<?, ?>) ((Map<?, ?>) reconnected.load(secondId).get("characters"))
                    .get("林默")).containsKey("runtime_state"));
        }

        // Phase 2 在一个快照中保存已消费提醒、新提醒和带来源的事件队列。
        var phase2Runtime = new HashMap<String, Object>(runtime);
        phase2Runtime.put("agenda", List.of(
                Map.of("id", "visit", "character", "林默", "due_tick", 310,
                        "intention", "继续调查", "status", "completed"),
                Map.of("id", "next-visit", "character", "林默", "due_tick", 314,
                        "intention", "重新考虑新线索", "status", "pending")));
        phase2Runtime.put("busy_until", 310);
        var phase2Scheduler = Map.of("tick_count", 311, "event_cursor", 0, "current_depth", 1,
                "pending", List.of(Map.of("name", "苏晚", "depth", 1, "source", "event")));
        linPayload.put("runtime_state", phase2Runtime);
        payload.put("scheduler", phase2Scheduler);
        tools.saveAgentState(firstId, mapper.writeValueAsString(payload));
        assertEquals(phase2Scheduler, reconnected.load(firstId).get("scheduler"));
        assertEquals(phase2Runtime, ((Map<?, ?>) ((Map<?, ?>) reconnected.load(firstId).get("characters"))
                .get("林默")).get("runtime_state"));
        // 世界规则只结算世界行动，不把成功行动自动当成 Agenda / Plan 完成。
        tools.executeWorldTool(firstId, "inspect", "{\"character\":\"林默\"}", "林默");
        assertEquals(phase2Runtime, ((Map<?, ?>) ((Map<?, ?>) reconnected.load(firstId).get("characters"))
                .get("林默")).get("runtime_state"));
        assertEquals(0, ((Map<?, ?>) reconnected.load(secondId).get("scheduler")).get("tick_count"));
        assertEquals(3, ((List<?>) ((Map<?, ?>) reconnected.load(secondId).get("scheduler")).get("pending")).size());

        // Python 清理后的当前 Agenda 替换旧列表，Java 快照不追加历史，也不改变世界业务字段。
        for (int round = 0; round < 40; round++) {
            phase2Runtime.put("agenda", List.of(Map.of("id", "pending-" + round, "character", "林默",
                    "due_tick", 320 + round, "intention", "再次考虑调查方向", "status", "pending")));
            tools.saveAgentState(firstId, mapper.writeValueAsString(payload));
            var current = (Map<?, ?>) ((Map<?, ?>) reconnected.load(firstId).get("characters")).get("林默");
            assertEquals(phase2Runtime, current.get("runtime_state"));
            assertEquals(1, ((List<?>) ((Map<?, ?>) current.get("runtime_state")).get("agenda")).size());
            assertEquals("县衙", current.get("location"));
        }
        phase2Runtime.put("agenda", List.of());
        tools.saveAgentState(firstId, mapper.writeValueAsString(payload));
        assertEquals(phase2Runtime, ((Map<?, ?>) ((Map<?, ?>) reconnected.load(firstId).get("characters"))
                .get("林默")).get("runtime_state"));

        for (var invalid : List.of(Map.of("location", "晚风客栈"),
                Map.of("current_plan", List.of("move", "inspect")),
                Map.of("active_goal", "别人的目标"), Map.of("busy_until", true),
                Map.of("agenda", List.of(Map.of("id", "x", "character", "苏晚", "due_tick", 1, "intention", "藏匿"))))) {
            linPayload.put("runtime_state", invalid);
            var savedBefore = store.load(firstId);
            assertThrows(IllegalArgumentException.class,
                    () -> tools.saveAgentState(firstId, mapper.writeValueAsString(payload)));
            assertEquals(savedBefore, store.load(firstId));
        }
    }

    @Test void interventionIsVisibleOnlyAtItsLocationAndReadableByCursor() {
        var store = mock(WorldStore.class);
        var world = new HashMap<String, Object>();
        world.put("time", "08:15");
        world.put("revision", 0);
        world.put("locations", List.of("客栈", "县衙"));
        world.put("inspectable_objects", new HashMap<String, Object>());
        world.put("events", new ArrayList<>());
        world.put("characters", Map.of("甲", Map.of("location", "客栈"), "乙", Map.of("location", "县衙")));
        when(store.load("test-world")).thenReturn(world);
        var tools = new WorldMcpTools(store, new WorldRules(), new ObjectMapper());

        assertThrows(IllegalArgumentException.class,
                () -> tools.injectWorldEvent("test-world", "王宫", "信", "内容"));
        assertEquals(0, ((List<?>) world.get("events")).size());
        var event = tools.injectWorldEvent("test-world", "客栈", "信", "失踪者留下的字迹");
        assertEquals(List.of("甲"), event.get("perceived_by"));
        assertEquals("intervention", event.get("type"));
        assertTrue(tools.getWorldEvents("test-world", 0).contains("失踪者留下的字迹"));
        assertTrue(tools.getWorldEvents("test-world", 1).contains("\"events\":[]"));
        verify(store).update(eq("test-world"), same(world));
    }

    @Test void directorAddsInspectableEventWithoutMovingAnyone() {
        var store = mock(WorldStore.class);
        var world = new HashMap<String, Object>();
        world.put("time", "08:15");
        world.put("revision", 0);
        world.put("locations", List.of("晚风客栈"));
        world.put("inspectable_objects", new HashMap<String, Object>());
        world.put("events", new ArrayList<>());
        world.put("characters", Map.of("苏晚", Map.of("location", "晚风客栈")));
        when(store.load("test-world")).thenReturn(world);
        var tools = new WorldMcpTools(store, new WorldRules(), new ObjectMapper());

        String json = tools.introduceNarrativeEvent("test-world", "stagnation", "晚风客栈", "匿名纸条", 3);

        assertTrue(json.contains("director"));
        assertEquals(1, ((List<?>) world.get("events")).size());
        assertFalse(((Map<?, ?>) ((Map<?, ?>) world.get("inspectable_objects")).get("晚风客栈")).isEmpty());
        assertEquals("晚风客栈", ((Map<?, ?>) ((Map<?, ?>) world.get("characters")).get("苏晚")).get("location"));
        verify(store).update(eq("test-world"), same(world));
    }
}
