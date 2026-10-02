package org.novelworld.world;

import java.util.*;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

class PlayerActorTest {
    final ObjectPersistenceTest fixture = new ObjectPersistenceTest();
    Map<String, Object> world() { return fixture.store.load(fixture.id); }
    Map<String, Object> player() { return WorldActors.player(world()); }
    Map<String, Object> object(String name) { return fixture.named(world(), name); }
    void act(String tool, Object... values) {
        var args = new LinkedHashMap<String, Object>();
        args.put(tool.equals("talk") ? "speaker" : "character", "玩家");
        for (int i = 0; i < values.length; i += 2) args.put((String) values[i], values[i + 1]);
        fixture.act(tool, args, "玩家");
    }
    void reject(String tool, Object... values) {
        var before = world();
        assertThrows(IllegalArgumentException.class, () -> act(tool, values));
        assertEquals(before, world(), "拒绝不提交事件、物理状态或时钟");
    }
    Map<String, Object> lastEvent() {
        var events = WorldObjects.list(world().get("events"));
        return WorldObjects.map(events.get(events.size() - 1));
    }

    @Test void playerIsMinimalPersistedActorAndNotBootstrapNpc() {
        assertEquals(Set.of("name", "location", "energy", "hp", "status", "items", "relationships", "actor_type"), player().keySet());
        assertEquals("player", player().get("actor_type"));
        assertEquals(player(), WorldActors.player(new WorldStore(fixture.jdbc, fixture.mapper).load(fixture.id)));
        var pending = WorldObjects.list(WorldObjects.map(world().get("scheduler")).get("pending"));
        assertEquals(3, pending.size());
        assertTrue(pending.stream().map(WorldObjects::map).noneMatch(entry -> "玩家".equals(entry.get("name"))));
    }
    @Test void legacyWorldDeterministicallyMigratesAndAvoidsNpcNameCollision() {
        var old = world(); var actors = WorldObjects.map(old.get("characters")); actors.remove("玩家");
        var npc = new LinkedHashMap<>(WorldObjects.map(actors.get("苏晚"))); npc.put("name", "玩家"); npc.remove("actor_type"); actors.put("玩家", npc);
        fixture.jdbc.update("UPDATE world_saves SET snapshot = ? WHERE world_id = ?", fixture.mapper.writeValueAsString(old), fixture.id);
        var migrated = world();
        assertEquals("玩家2", WorldActors.player(migrated).get("name"));
        assertEquals(migrated, world());
        fixture.store.update(fixture.id, migrated);
        assertTrue(fixture.jdbc.queryForObject("SELECT snapshot FROM world_saves WHERE world_id = ?", String.class, fixture.id).contains("玩家2"));
    }
    @Test void templateSupportsConfiguredPlayerAndRejectsCollisionsAndInvalidLocations() {
        var templates = new WorldTemplateService(fixture.store, fixture.mapper);
        var template = templates.defaultTemplate(); template.put("player", Map.of("name", "旅人", "location", "青石街"));
        var id = templates.createWorld(template);
        assertEquals("青石街", WorldActors.player(fixture.store.load(id)).get("location"));
        template.put("player", Map.of("name", "苏晚", "location", "晚风客栈"));
        assertThrows(IllegalArgumentException.class, () -> templates.createWorld(template));
        template.put("player", Map.of("name", "旅人", "location", "不存在"));
        assertThrows(IllegalArgumentException.class, () -> templates.createWorld(template));
    }
    @Test void playerInspectUsesPrivateRealEventAndCostsEnergy() {
        act("inspect", "object_id", object("住客登记簿").get("id"));
        assertEquals("inspect", lastEvent().get("type"));
        assertEquals(List.of("玩家"), lastEvent().get("perceived_by"));
        assertEquals(97, player().get("energy"));
        reject("inspect", "object_id", object("住客登记簿").get("id"));
    }
    @Test void playerTakePutAndGiveUseAuthoritativeHolderAndDerivedInventory() {
        Object id = object("住客登记簿").get("id");
        act("take", "object_id", id);
        assertEquals("玩家", object("住客登记簿").get("holder"));
        assertEquals(List.of("住客登记簿"), player().get("items"));
        assertTrue(((List<?>) lastEvent().get("perceived_by")).containsAll(List.of("玩家", "苏晚")));
        act("put", "object_id", id, "location", "晚风客栈");
        assertNull(object("住客登记簿").get("holder"));
        act("take", "object_id", id); act("give", "object_id", id, "receiver", "苏晚");
        assertEquals("苏晚", object("住客登记簿").get("holder"));
        assertEquals(List.of(), player().get("items"));
        assertEquals(List.of("玩家", "苏晚"), lastEvent().get("perceived_by"));
        assertNull(fixture.named(fixture.store.load(fixture.otherId), "住客登记簿").get("holder"));
    }
    @Test void playerInteractPutContainerAndClosedContentsUseSameRules() {
        Object book = object("住客登记簿").get("id"), chest = object("木箱").get("id");
        act("take", "object_id", book); reject("put", "object_id", book, "container_id", chest);
        act("interact", "object_id", chest, "action", "open");
        act("put", "object_id", book, "container_id", chest);
        act("interact", "object_id", chest, "action", "close");
        assertFalse(WorldObjects.visible(world(), object("住客登记簿"), "玩家"));
        reject("inspect", "object_id", book); reject("take", "object_id", book);
        act("interact", "object_id", chest, "action", "open"); act("take", "object_id", book);
        assertEquals("玩家", object("住客登记簿").get("holder"));
    }
    @Test void playerUseConsumesOnlyHeldDeclaredMedicineAndLampStateIsChecked() {
        var world = world(); var key = fixture.named(world, "钥匙");
        key.put("affordances", List.of("consume")); WorldObjects.map(key.get("properties")).put("heal", 20);
        WorldActors.player(world).put("hp", 60); fixture.store.update(fixture.id, world);
        reject("use", "object_id", key.get("id"), "action", "consume");
        act("take", "object_id", key.get("id")); act("use", "object_id", key.get("id"), "action", "consume");
        assertEquals(80, player().get("hp")); assertEquals("consumed", object("钥匙").get("state"));
        reject("use", "object_id", key.get("id"), "action", "consume");
        world = world(); var lamp = WorldObjects.object("lamp-id", "灯", "晚风客栈", "普通灯");
        lamp.put("state", "extinguished"); lamp.put("affordances", List.of("light", "extinguish"));
        WorldObjects.map(world.get("objects")).put("lamp-id", lamp); fixture.store.update(fixture.id, world);
        act("use", "object_id", "lamp-id", "action", "light"); assertEquals("lit", object("灯").get("state"));
        reject("use", "object_id", "lamp-id", "action", "light");
        act("use", "object_id", "lamp-id", "action", "extinguish");
    }
    @Test void hiddenDistantNonPortableNonHeldAndIllegalAffordanceAreRejected() {
        var world = world(); var book = fixture.named(world, "住客登记簿"); book.put("visible", false);
        fixture.store.update(fixture.id, world);
        reject("take", "object_id", book.get("id")); reject("inspect", "object_id", book.get("id"));
        reject("take", "object_id", object("后门").get("id"));
        reject("give", "object_id", object("钥匙").get("id"), "receiver", "苏晚");
        reject("interact", "object_id", object("后门").get("id"), "action", "拆门");
        reject("move_character", "location", "虚构地点");
        reject("talk", "listener", "林默", "message", "远程对话");
        act("move_character", "location", "县衙");
        reject("take", "object_id", object("钥匙").get("id"));
    }
    @Test void energyAndIncapacitationDoNotGrantPlayerGodMode() {
        var world = world(); WorldActors.player(world).put("energy", 0); fixture.store.update(fixture.id, world);
        reject("inspect"); reject("move_character", "location", "县衙");
        act("rest_character"); assertEquals(20, player().get("energy"));
        world = world(); WorldActors.player(world).put("status", "unconscious"); fixture.store.update(fixture.id, world);
        reject("take", "object_id", object("钥匙").get("id"));
    }
    @Test void spoofedActorAndRelationshipToolsCannotCommit() {
        var before = world();
        for (String tool : List.of("inspect", "take", "move_character", "talk")) {
            var args = tool.equals("talk") ? Map.<String, Object>of("speaker", "苏晚", "listener", "玩家", "message", "伪造")
                    : Map.<String, Object>of("character", "苏晚", "location", "县衙", "object_id", object("钥匙").get("id"));
            assertThrows(IllegalArgumentException.class, () -> fixture.act(tool, args, "玩家"));
        }
        reject("update_relationship", "target", "苏晚", "change", 20);
        reject("world_action", "actor", "玩家", "action", "attack", "target", "苏晚");
        assertEquals(before, world());
    }
    @Test void actualPlayerTalkSessionAndNpcTurnPersistWithoutPlayerCognition() {
        act("talk", "listener", "苏晚", "message", "你好"); var first = lastEvent();
        fixture.act("talk", Map.of("speaker", "苏晚", "listener", "玩家", "message", "欢迎"), "苏晚"); var second = lastEvent();
        var session = Map.of("id", "player-session", "participants", List.of("玩家", "苏晚"), "location", "晚风客栈",
                "started_tick", 0, "last_activity_tick", 1, "next_speaker", "玩家", "status", "active", "messages", List.of(
                        Map.of("speaker", "玩家", "content", "你好", "tick", 0, "event_id", first.get("id")),
                        Map.of("speaker", "苏晚", "content", "欢迎", "tick", 1, "event_id", second.get("id"))));
        var payload = Map.of("characters", ObjectPersistenceTest.npcs(world().get("characters")),
                "scheduler", Map.of("tick_count", 2), "active_conversations", List.of(session));
        fixture.tools.saveAgentState(fixture.id, fixture.mapper.writeValueAsString(payload));
        var restored = new WorldStore(fixture.jdbc, fixture.mapper).load(fixture.id);
        assertEquals(List.of(session), restored.get("active_conversations"));
        assertFalse(WorldActors.player(restored).containsKey("runtime_state"));
        assertEquals(List.of("玩家", "苏晚"), first.get("perceived_by"));
        assertFalse(fixture.store.load(fixture.otherId).containsKey("active_conversations"));
    }
    @Test void agentSaveCannotCreatePlayerMemoryOrOverwritePlayerBusiness() {
        var world = world(); var before = player();
        var npcs = ObjectPersistenceTest.npcs(world.get("characters"));
        npcs.put("玩家", Map.of("runtime_state", Map.of("busy_until", 99), "location", "县衙"));
        assertThrows(IllegalArgumentException.class, () -> fixture.tools.saveAgentState(fixture.id, fixture.mapper.writeValueAsString(
                Map.of("characters", npcs, "scheduler", Map.of("tick_count", 2)))));
        assertEquals(before, player());
        fixture.tools.saveAgentState(fixture.id, fixture.mapper.writeValueAsString(Map.of("characters", ObjectPersistenceTest.npcs(world.get("characters")),
                "player", Map.of("energy", 0), "scheduler", Map.of("tick_count", 2))));
        assertEquals(before, player());
    }
    @Test void playWebRoutesRemainJavaEntryAndObserveKeepsNpcMemoryViews() throws Exception {
        var runtime = mock(AgentRuntimeClient.class);
        when(runtime.status()).thenReturn(Map.of("world_id", fixture.id, "tick_count", 0, "running", false, "error", ""));
        when(runtime.play(eq("state"), anyMap())).thenReturn(Map.of("player", Map.of("name", "玩家")));
        when(runtime.play(eq("action"), anyMap())).thenReturn(Map.of("committed", true));
        when(runtime.play(eq("conversation/end"), anyMap())).thenReturn(Map.of("ended", true));
        var controller = new WorldWebController(fixture.store, runtime, fixture.mapper);
        var mvc = org.springframework.test.web.servlet.setup.MockMvcBuilders.standaloneSetup(controller).build();
        mvc.perform(get("/api/play/state")).andExpect(status().isOk()).andExpect(jsonPath("$.player.name").value("玩家"));
        mvc.perform(post("/api/play/action").contentType("application/json").content("{\"world_id\":\"w\",\"action\":\"inspect\"}"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.committed").value(true));
        mvc.perform(post("/api/play/conversation/end").contentType("application/json").content("{\"world_id\":\"w\"}"))
                .andExpect(status().isOk());
        mvc.perform(get("/api/world")).andExpect(status().isOk()).andExpect(jsonPath("$.characters.玩家").doesNotExist());
        mvc.perform(get("/api/characters/苏晚/view")).andExpect(status().isOk()).andExpect(jsonPath("$.goals").isArray());
        mvc.perform(get("/api/characters/玩家/view")).andExpect(status().isNotFound());
        assertEquals(Set.of("world_id", "tick_count", "running", "time", "event_count", "revision"),
                WorldWebController.playRefresh(world(), runtime.status()).keySet());
        assertFalse(WorldWebController.playRefresh(world(), runtime.status()).toString().contains("goals"));
    }
}
