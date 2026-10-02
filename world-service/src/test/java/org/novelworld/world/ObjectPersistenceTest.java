package org.novelworld.world;

import java.util.*;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.ObjectMapper;
import static org.junit.jupiter.api.Assertions.*;

class ObjectPersistenceTest {
    final ObjectMapper mapper = new ObjectMapper();
    final org.springframework.jdbc.core.JdbcTemplate jdbc;
    final WorldStore store;
    final WorldMcpTools tools;
    final String id;
    final String otherId;
    ObjectPersistenceTest() {
        var source = new org.h2.jdbcx.JdbcDataSource();
        source.setURL("jdbc:h2:mem:objects-" + UUID.randomUUID() + ";DB_CLOSE_DELAY=-1");
        jdbc = new org.springframework.jdbc.core.JdbcTemplate(source);
        jdbc.execute("CREATE TABLE world_saves (world_id VARCHAR(64) PRIMARY KEY, snapshot CLOB NOT NULL, revision BIGINT NOT NULL)");
        store = new WorldStore(jdbc, mapper); var templates = new WorldTemplateService(store, mapper);
        id = templates.createWorld(templates.defaultTemplate()); otherId = templates.createWorld(templates.defaultTemplate());
        tools = new WorldMcpTools(store, new WorldRules(), mapper);
    }
    Map<String, Object> named(Map<String, Object> world, String name) {
        return WorldObjects.map(world.get("objects")).values().stream().map(WorldObjects::map)
                .filter(obj -> name.equals(obj.get("name"))).findFirst().orElseThrow();
    }
    void act(String tool, Map<String, Object> args, String actor) {
        tools.executeWorldTool(id, tool, mapper.writeValueAsString(args), actor);
    }
    void move() { act("move_character", Map.of("character", "林默", "location", "晚风客栈"), "林默"); }
    static Map<String, Object> npcs(Object raw) {
        var result = new LinkedHashMap<String, Object>();
        WorldObjects.map(raw).forEach((name, actor) -> { if (WorldActors.isNpc(WorldObjects.map(actor))) result.put(name, actor); });
        return result;
    }
    @Test void heldObjectsPersistAcrossDatabaseReconnectAndWorldsStayIndependent() {
        move(); var book = named(store.load(id), "住客登记簿");
        act("take", Map.of("character", "林默", "object_id", book.get("id")), "林默");
        var restored = new WorldStore(jdbc, mapper).load(id);
        assertEquals("林默", named(restored, "住客登记簿").get("holder"));
        assertNull(named(restored, "住客登记簿").get("location"));
        assertEquals("晚风客栈", named(store.load(otherId), "住客登记簿").get("location"));
        assertNull(named(store.load(otherId), "住客登记簿").get("holder"));
    }
    @Test void containerAndStatePersistInExistingSnapshotTable() {
        move(); var book = named(store.load(id), "住客登记簿"); var chest = named(store.load(id), "木箱");
        act("take", Map.of("character", "林默", "object_id", book.get("id")), "林默");
        act("interact", Map.of("character", "林默", "object_id", chest.get("id"), "action", "open"), "林默");
        act("put", Map.of("character", "林默", "object_id", book.get("id"), "container_id", chest.get("id")), "林默");
        act("interact", Map.of("character", "林默", "object_id", chest.get("id"), "action", "close"), "林默");
        var world = new WorldStore(jdbc, mapper).load(id);
        assertEquals(chest.get("id"), named(world, "住客登记簿").get("container")); assertEquals("closed", named(world, "木箱").get("state"));
        assertFalse(WorldObjects.visible(world, named(world, "住客登记簿"), "苏晚"));
    }
    @Test void runtimeSaveCannotOverrideObjectsOrInventInventory() {
        var before = store.load(id); var payload = new LinkedHashMap<String, Object>();
        var characters = mapper.readValue(mapper.writeValueAsString(before.get("characters")), Map.class);
        WorldObjects.map(characters.get("林默")).put("items", List.of("凭空钥匙"));
        payload.put("characters", npcs(characters)); payload.put("objects", Map.of());
        payload.put("inspectable_objects", Map.of()); payload.put("scheduler", Map.of("tick_count", 1));
        tools.saveAgentState(id, mapper.writeValueAsString(payload));
        var after = store.load(id); assertEquals(before.get("objects"), after.get("objects"));
        assertEquals(WorldObjects.map(WorldObjects.map(before.get("characters")).get("林默")).get("items"),
                WorldObjects.map(WorldObjects.map(after.get("characters")).get("林默")).get("items"));
    }
    @Test void forgedActorAndFailedActionsDoNotCommitSnapshots() {
        move(); var before = store.load(id); var book = named(before, "住客登记簿");
        assertThrows(IllegalArgumentException.class, () -> act("take", Map.of("character", "苏晚", "object_id", book.get("id")), "林默"));
        assertThrows(IllegalArgumentException.class, () -> act("put", Map.of("character", "林默", "object_id", book.get("id"), "location", "县衙"), "林默"));
        assertEquals(before, store.load(id));
    }
    @Test void trueLegacyDatabaseSnapshotMigratesWithStableIdsAndHiddenTrace() {
        var old = store.load(id); old.remove("objects"); old.put("version", 1);
        old.put("inspectable_objects", Map.of("晚风客栈", Map.of("住客登记簿被移动的痕迹", "移动痕迹")));
        old.put("concealable_objects", Map.of("晚风客栈", List.of("住客登记簿")));
        old.put("concealed_objects", Map.of("晚风客栈", Map.of("住客登记簿", Map.of("observation", "旧内容",
                "trace_name", "住客登记簿被移动的痕迹", "concealed_at_event_count", 1))));
        // legacy history only：旧痕迹曾被调查，之后藏匿改变其观察世代。
        WorldObjects.list(old.get("events")).add(Map.of("type", "inspect", "actor", "苏晚", "location", "晚风客栈",
                "payload", Map.of("object_name", "住客登记簿被移动的痕迹", "observation", "移动痕迹 状态：normal")));
        WorldObjects.list(old.get("events")).add(Map.of("type", "conceal", "actor", "苏晚", "location", "晚风客栈", "payload", Map.of()));
        jdbc.update("UPDATE world_saves SET snapshot = ? WHERE world_id = ?", mapper.writeValueAsString(old), id);
        var migrated = store.load(id); assertEquals(migrated, store.load(id)); assertEquals(2, migrated.get("version"));
        assertEquals(false, named(migrated, "住客登记簿").get("visible"));
        assertEquals(WorldObjects.stableId("scene\0晚风客栈\0住客登记簿"), named(migrated, "住客登记簿").get("id"));
        assertEquals("林默", named(migrated, "捕快腰牌").get("holder"));
        var trace = named(migrated, "住客登记簿被移动的痕迹");
        assertEquals(Map.of("hidden_at_index", 1), trace.get("properties")); assertEquals(false, trace.get("portable"));
        var inspectArgs = Map.of("character", "苏晚", "object_id", trace.get("id"));
        new WorldRules().apply(migrated, "inspect", inspectArgs); // 不被隐藏前的旧调查误拒绝。
        assertThrows(IllegalArgumentException.class, () -> new WorldRules().apply(migrated, "inspect", inspectArgs));
        store.update(id, migrated);
        var saved = mapper.readValue(jdbc.queryForObject("SELECT snapshot FROM world_saves WHERE world_id = ?", String.class, id), Map.class);
        assertTrue(saved.containsKey("objects")); assertEquals(2, saved.get("version"));
        for (String field : List.of("inspectable_objects", "concealable_objects", "concealed_objects")) assertFalse(saved.containsKey(field));
        // 旧 canonical V1 标记也在加载边界清除，不重新生成旧投影。
        saved.put("version", 1);
        WorldObjects.map(named(saved, "住客登记簿").get("properties")).put("legacy_concealable", true);
        WorldObjects.map(named(saved, "住客登记簿被移动的痕迹").get("properties")).put("trace_for", named(saved, "住客登记簿").get("id"));
        jdbc.update("UPDATE world_saves SET snapshot = ? WHERE world_id = ?", mapper.writeValueAsString(saved), id);
        assertEquals(mapper.readValue(mapper.writeValueAsString(migrated), Map.class), store.load(id));
    }

    @Test void interventionAddsCanonicalObjectAndCannotOverwriteMovedObject() {
        tools.injectWorldEvent(id, "晚风客栈", "纸条", "真实内容");
        move(); var note = named(store.load(id), "纸条"); act("take", Map.of("character", "林默", "object_id", note.get("id")), "林默");
        var before = store.load(id);
        assertThrows(IllegalArgumentException.class, () -> tools.injectWorldEvent(id, "晚风客栈", "纸条", "覆盖内容"));
        assertEquals(before, store.load(id));
    }
    @Test void explicitObjectTemplateIsValidatedAndProjected() {
        var templates = new WorldTemplateService(store, mapper); var template = templates.defaultTemplate();
        var item = WorldObjects.object("template-key", "通用钥匙", "县衙", "普通物件");
        template.put("objects", Map.of("template-key", item));
        var created = store.load(templates.createWorld(template));
        assertEquals(Set.of("template-key"), WorldObjects.map(created.get("objects")).keySet());
        assertEquals(List.of(), WorldObjects.map(WorldObjects.map(created.get("characters")).get("林默")).get("items"));
        WorldObjects.map(item.get("properties")).put("legacy_concealable", true);
        assertThrows(IllegalArgumentException.class, () -> templates.createWorld(template));
        WorldObjects.map(item.get("properties")).clear();
        item.put("affordances", List.of("执行任意脚本"));
        assertThrows(IllegalArgumentException.class, () -> templates.createWorld(template));
    }
}
