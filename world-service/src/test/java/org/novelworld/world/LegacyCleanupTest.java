package org.novelworld.world;

import java.util.*;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class LegacyCleanupTest {
    final ObjectPersistenceTest fixture = new ObjectPersistenceTest();

    @Test void runtimeCannotAppendEvenNarrationAndRejectionIsAtomic() {
        var before = fixture.store.load(fixture.id);
        var payload = new LinkedHashMap<String, Object>();
        payload.put("characters", before.get("characters")); payload.put("scheduler", Map.of("tick_count", 20));
        payload.put("events", List.of(Map.of("id", "invented", "type", "narration", "description", "模型声称已拿取")));
        assertThrows(IllegalArgumentException.class, () -> fixture.tools.saveAgentState(fixture.id, fixture.mapper.writeValueAsString(payload)));
        assertEquals(before, fixture.store.load(fixture.id));
    }
    @Test void historicalNarrationRemainsInLegacySnapshotButEmptyOldPayloadDoesNotAppend() {
        var legacy = fixture.store.load(fixture.id);
        WorldObjects.list(legacy.get("events")).add(Map.of("id", "old-text", "type", "narration", "actor", "林默", "description", "旧叙述"));
        fixture.jdbc.update("UPDATE world_saves SET snapshot = ? WHERE world_id = ?", fixture.mapper.writeValueAsString(legacy), fixture.id);
        fixture.tools.saveAgentState(fixture.id, fixture.mapper.writeValueAsString(Map.of("characters", ObjectPersistenceTest.npcs(legacy.get("characters")),
                "scheduler", legacy.get("scheduler"), "events", List.of())));
        assertEquals(legacy.get("events"), fixture.store.load(fixture.id).get("events"));
    }
    @Test void newWorldExplicitlyStoresOneBootstrapPerNpc() {
        var world = fixture.store.load(fixture.id);
        var scheduler = WorldObjects.map(world.get("scheduler"));
        assertEquals(0, scheduler.get("tick_count")); assertEquals(0, scheduler.get("event_cursor"));
        var pending = WorldObjects.list(scheduler.get("pending"));
        assertEquals(ObjectPersistenceTest.npcs(world.get("characters")).size(), pending.size());
        assertEquals(pending.size(), pending.stream().map(WorldObjects::map).map(item -> item.get("name")).distinct().count());
        assertTrue(pending.stream().map(WorldObjects::map).allMatch(item -> "bootstrap".equals(item.get("source"))));
        assertFalse(scheduler.containsKey("skill_views"));
    }
    @Test void retainedExternalAliasesNormalizeIntoAuthoritativePrimitives() {
        fixture.move(); var world = fixture.store.load(fixture.id); var book = fixture.named(world, "住客登记簿");
        fixture.act("take", Map.of("character", "林默", "object_id", book.get("id")), "林默");
        fixture.act("give_item", Map.of("giver", "林默", "receiver", "苏晚", "item", "住客登记簿"), "林默");
        var after = fixture.store.load(fixture.id);
        assertEquals("苏晚", fixture.named(after, "住客登记簿").get("holder"));
        assertEquals("give", WorldObjects.map(WorldObjects.list(after.get("events")).get(2)).get("type"));
        var door = fixture.named(after, "后门");
        fixture.act("world_action", Map.of("actor", "林默", "action", "interact", "object_id", door.get("id"), "interaction", "open"), "林默");
        assertEquals("open", fixture.named(fixture.store.load(fixture.id), "后门").get("state"));
        assertThrows(IllegalArgumentException.class, () -> fixture.act("world_action", Map.of("actor", "林默", "action", "interact", "object_id", door.get("id")), "林默"));
        var saved = fixture.store.load(fixture.id);
        assertThrows(IllegalArgumentException.class, () -> fixture.act("give_item", Map.of("giver", "苏晚", "receiver", "林默", "item", "住客登记簿"), "林默"));
        assertEquals(saved, fixture.store.load(fixture.id));
    }
    @Test void removedPlotToolsFailAtMcpWithoutChangingSnapshot() {
        var before = fixture.store.load(fixture.id);
        for (String tool : List.of("conceal_clue", "recover_clue"))
            assertThrows(IllegalArgumentException.class, () -> fixture.act(tool, Map.of("character", "苏晚", "object_name", "住客登记簿"), "苏晚"));
        assertEquals(before, fixture.store.load(fixture.id));
    }
    @Test void externalUseItemAliasRequiresARealHeldObjectAndConsumesIt() {
        var world = fixture.store.load(fixture.id);
        var medicine = WorldObjects.object("legacy-medicine", "普通药物", null, "药物");
        medicine.put("holder", "林默"); medicine.put("owner", "林默");
        medicine.put("affordances", List.of("consume")); WorldObjects.map(medicine.get("properties")).put("heal", 20);
        WorldObjects.map(world.get("objects")).put("legacy-medicine", medicine);
        WorldObjects.map(WorldObjects.map(world.get("characters")).get("林默")).put("hp", 60);
        fixture.store.update(fixture.id, world);
        fixture.act("world_action", Map.of("actor", "林默", "action", "use_item", "item", "普通药物"), "林默");
        var saved = fixture.store.load(fixture.id);
        assertEquals("consumed", fixture.named(saved, "普通药物").get("state"));
        assertNull(fixture.named(saved, "普通药物").get("holder"));
        assertEquals(80, WorldObjects.map(WorldObjects.map(saved.get("characters")).get("林默")).get("hp"));
    }
    @Test void injectionChecksCanonicalClosedContentsWithCustomIds() {
        var world = fixture.store.load(fixture.id); var chest = fixture.named(world, "木箱");
        var note = WorldObjects.object("custom-hidden-note", "隐蔽纸条", null, "内容不能泄漏");
        note.put("container", chest.get("id")); WorldObjects.map(world.get("objects")).put("custom-hidden-note", note);
        fixture.store.update(fixture.id, world); var before = fixture.store.load(fixture.id);
        assertFalse(WorldObjects.map(before.get("inspectable_objects")).toString().contains("隐蔽纸条"));
        assertThrows(IllegalArgumentException.class, () -> fixture.tools.injectWorldEvent(fixture.id, "晚风客栈", "隐蔽纸条", "新内容"));
        assertEquals(before, fixture.store.load(fixture.id));
    }
}
