package org.novelworld.world;

import java.util.ArrayList;
import java.util.Map;
import org.h2.jdbcx.JdbcDataSource;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import tools.jackson.databind.ObjectMapper;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class WorldTemplateServiceTest {
    @Test
    @SuppressWarnings("unchecked")
    void twoOpeningsRemainIndependentInDatabase() {
        var source = new JdbcDataSource();
        source.setURL("jdbc:h2:mem:opening-test;DB_CLOSE_DELAY=-1");
        var jdbc = new JdbcTemplate(source);
        jdbc.execute("CREATE TABLE IF NOT EXISTS world_saves (world_id VARCHAR(64) PRIMARY KEY, snapshot CLOB NOT NULL, revision BIGINT NOT NULL)");
        var store = new WorldStore(jdbc, new ObjectMapper());
        var service = new WorldTemplateService(store, new ObjectMapper());
        var original = service.defaultTemplate();
        var changed = service.defaultTemplate();
        ((Map<String, Object>) ((Map<String, Object>) changed.get("characters")).get("林默"))
                .put("goals", java.util.List.of("寻找遗失的信"));

        String firstId = service.createWorld(original);
        String secondId = service.createWorld(changed);
        assertEquals(2, store.listWorldIds().size());
        assertEquals(java.util.List.of("做好县衙日常差事", "在镇民中建立可靠的声誉", "学会兼顾规矩与人情"),
                ((Map<?, ?>) ((Map<?, ?>) store.load(firstId).get("characters")).get("林默")).get("goals"));
        assertEquals(java.util.List.of("寻找遗失的信"),
                ((Map<?, ?>) ((Map<?, ?>) store.load(secondId).get("characters")).get("林默")).get("goals"));
        var firstWorld = store.load(firstId);
        firstWorld.put("time", "09:00");
        store.update(firstId, firstWorld);
        assertEquals(1, store.load(firstId).get("revision"));
        assertEquals("08:00", store.load(secondId).get("time"));
    }

    @Test
    @SuppressWarnings("unchecked")
    void takenObjectStaysInItsOwnWorld() {
        var source = new JdbcDataSource();
        source.setURL("jdbc:h2:mem:conceal-isolation;DB_CLOSE_DELAY=-1");
        var jdbc = new JdbcTemplate(source);
        jdbc.execute("CREATE TABLE IF NOT EXISTS world_saves (world_id VARCHAR(64) PRIMARY KEY, snapshot CLOB NOT NULL, revision BIGINT NOT NULL)");
        var store = new WorldStore(jdbc, new ObjectMapper());
        var service = new WorldTemplateService(store, new ObjectMapper());
        String firstId = service.createWorld(service.defaultTemplate());
        String secondId = service.createWorld(service.defaultTemplate());
        var first = store.load(firstId);
        new WorldRules().apply(first, "take", Map.of("character", "苏晚", "object_id", WorldObjects.stableId("scene\0晚风客栈\0住客登记簿")));
        store.update(firstId, first);
        String bookId = WorldObjects.stableId("scene\0晚风客栈\0住客登记簿");
        var firstBook = WorldObjects.map(WorldObjects.map(store.load(firstId).get("objects")).get(bookId));
        var secondBook = WorldObjects.map(WorldObjects.map(store.load(secondId).get("objects")).get(bookId));
        assertEquals("苏晚", firstBook.get("holder"));
        assertNull(secondBook.get("holder")); assertEquals("晚风客栈", secondBook.get("location"));
        for (String field : java.util.List.of("inspectable_objects", "concealable_objects", "concealed_objects"))
            assertFalse(store.load(firstId).containsKey(field));
    }

    @Test
    @SuppressWarnings("unchecked")
    void editedOpeningsCreateIndependentEmptyWorlds() {
        var store = mock(WorldStore.class);
        var service = new WorldTemplateService(store, new ObjectMapper());
        var first = service.defaultTemplate();
        var second = service.defaultTemplate();
        ((Map<String, Object>) ((Map<String, Object>) second.get("characters")).get("林默"))
                .put("goals", new ArrayList<>(java.util.List.of("寻找遗失的信")));

        String firstId = service.createWorld(first);
        String secondId = service.createWorld(second);

        var snapshots = ArgumentCaptor.forClass(Map.class);
        verify(store, times(2)).insert(anyString(), snapshots.capture());
        var oldWorld = snapshots.getAllValues().get(0);
        var newWorld = snapshots.getAllValues().get(1);
        assertNotEquals(firstId, secondId);
        assertEquals(firstId, oldWorld.get("world_id"));
        assertEquals(secondId, newWorld.get("world_id"));
        assertEquals(java.util.List.of("做好县衙日常差事", "在镇民中建立可靠的声誉", "学会兼顾规矩与人情"),
                ((Map<?, ?>) ((Map<?, ?>) oldWorld.get("characters")).get("林默")).get("goals"));
        assertEquals(java.util.List.of("寻找遗失的信"),
                ((Map<?, ?>) ((Map<?, ?>) newWorld.get("characters")).get("林默")).get("goals"));
        assertTrue(((java.util.List<?>) newWorld.get("events")).isEmpty());
        assertEquals(2, newWorld.get("version"));
        assertEquals(service.defaultTemplate().get("objects"), newWorld.get("objects"));
        for (String field : java.util.List.of("inspectable_objects", "concealable_objects", "concealed_objects")) {
            assertFalse(newWorld.containsKey(field)); assertFalse(service.defaultTemplate().containsKey(field));
        }
        assertFalse(((Map<?, ?>) ((Map<?, ?>) service.defaultTemplate().get("characters")).get("林默")).containsKey("items"));
        assertEquals(java.util.List.of("捕快腰牌"), ((Map<?, ?>) ((Map<?, ?>) newWorld.get("characters")).get("林默")).get("items"));
        assertFalse(((java.util.List<?>) newWorld.get("lore")).isEmpty());
        assertTrue(((java.util.List<?>) ((Map<?, ?>) ((Map<?, ?>) ((Map<?, ?>) newWorld.get("characters"))
                .get("林默")).get("memory")).get("entries")).isEmpty());
        assertFalse(service.defaultTemplate().containsKey("world_id"));
    }

    @Test
    @SuppressWarnings("unchecked")
    void invalidReferencesAreRejectedBeforeSaving() {
        var store = mock(WorldStore.class);
        var service = new WorldTemplateService(store, new ObjectMapper());
        var invalidLocation = service.defaultTemplate();
        ((Map<String, Object>) ((Map<String, Object>) invalidLocation.get("characters")).get("林默"))
                .put("location", "不存在的地点");
        assertThrows(IllegalArgumentException.class, () -> service.createWorld(invalidLocation));

        var invalidRelation = service.defaultTemplate();
        ((Map<String, Object>) ((Map<String, Object>) invalidRelation.get("characters")).get("林默"))
                .put("relationships", Map.of("陌生人", 10));
        assertThrows(IllegalArgumentException.class, () -> service.createWorld(invalidRelation));

        var invalidLore = service.defaultTemplate();
        ((java.util.List<Map<String, Object>>) invalidLore.get("lore")).get(0)
                .put("audience", "不存在的角色");
        assertThrows(IllegalArgumentException.class, () -> service.createWorld(invalidLore));
        var invalidConcealable = service.defaultTemplate();
        invalidConcealable.put("concealable_objects", Map.of("晚风客栈", java.util.List.of("不存在的线索")));
        assertThrows(IllegalArgumentException.class, () -> service.createWorld(invalidConcealable));
        var conflictingInventory = service.defaultTemplate();
        WorldObjects.map(WorldObjects.map(conflictingInventory.get("characters")).get("林默")).put("items", java.util.List.of("伪造物品"));
        assertThrows(IllegalArgumentException.class, () -> service.createWorld(conflictingInventory));
        var invalidHolder = service.defaultTemplate();
        var item = WorldObjects.map(WorldObjects.map(invalidHolder.get("objects")).values().iterator().next());
        item.put("holder", "不存在的人"); item.put("location", null);
        assertThrows(IllegalArgumentException.class, () -> service.createWorld(invalidHolder));
        verifyNoInteractions(store);
    }

    @Test
    void setupApiExposesTemplateAndReturnsBadRequestForInvalidOpening() throws Exception {
        var store = mock(WorldStore.class);
        var runtime = mock(AgentRuntimeClient.class);
        when(runtime.status()).thenReturn(Map.of("running", false));
        var service = new WorldTemplateService(store, new ObjectMapper());
        var mvc = MockMvcBuilders.standaloneSetup(new WorldSetupController(service, store, runtime)).build();
        mvc.perform(get("/api/world-template/default"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.characters.苏晚.secrets[0]").exists());
        mvc.perform(post("/api/worlds").contentType("application/json")
                        .content("{\"time\":\"invalid\"}"))
                .andExpect(status().isBadRequest());
        verifyNoInteractions(store);
    }

    @Test
    void activatingSavedWorldRequiresPauseAndDoesNotOverwriteAnotherWorld() throws Exception {
        var store = mock(WorldStore.class);
        var runtime = mock(AgentRuntimeClient.class);
        var service = new WorldTemplateService(store, new ObjectMapper());
        var mvc = MockMvcBuilders.standaloneSetup(new WorldSetupController(service, store, runtime)).build();
        when(store.listWorldIds()).thenReturn(java.util.List.of("old", "new"));
        when(store.load("new")).thenReturn(Map.of("world_id", "new"));
        when(runtime.status()).thenReturn(Map.of("world_id", "old", "running", true),
                Map.of("world_id", "old", "running", true),
                Map.of("world_id", "old", "running", false));
        when(runtime.control("activate", Map.of("world_id", "new")))
                .thenReturn(Map.of("world_id", "new", "running", false));

        mvc.perform(get("/api/worlds"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.world_ids.length()").value(2));
        mvc.perform(post("/api/worlds/new/activate")).andExpect(status().isConflict());
        mvc.perform(post("/api/worlds/new/activate"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.world_id").value("new"));
        verify(store, never()).update(anyString(), anyMap());
        verify(runtime).control("activate", Map.of("world_id", "new"));
    }

    @Test
    void deletingSavedWorldRemovesOnlyItsRecord() {
        var source = new JdbcDataSource();
        source.setURL("jdbc:h2:mem:delete-world-test;DB_CLOSE_DELAY=-1");
        var jdbc = new JdbcTemplate(source);
        jdbc.execute("CREATE TABLE world_saves (world_id VARCHAR(64) PRIMARY KEY, snapshot CLOB NOT NULL, revision BIGINT NOT NULL)");
        var store = new WorldStore(jdbc, new ObjectMapper());
        var service = new WorldTemplateService(store, new ObjectMapper());
        String removedId = service.createWorld(service.defaultTemplate());
        String keptId = service.createWorld(service.defaultTemplate());

        assertTrue(store.delete(removedId));
        assertFalse(store.delete(removedId));
        assertEquals(java.util.List.of(keptId), store.listWorldIds());
        assertThrows(IllegalArgumentException.class, () -> store.load(removedId));
        assertEquals(keptId, store.load(keptId).get("world_id"));
    }

    @Test
    void deleteApiRejectsRunningAndActiveWorlds() throws Exception {
        var store = mock(WorldStore.class);
        var runtime = mock(AgentRuntimeClient.class);
        var service = new WorldTemplateService(store, new ObjectMapper());
        var mvc = MockMvcBuilders.standaloneSetup(new WorldSetupController(service, store, runtime)).build();
        when(runtime.status()).thenReturn(
                Map.of("world_id", "current", "running", true),
                Map.of("world_id", "current", "running", false));
        when(store.delete("other")).thenReturn(true);

        mvc.perform(delete("/api/worlds/other")).andExpect(status().isConflict());
        mvc.perform(delete("/api/worlds/current")).andExpect(status().isConflict());
        mvc.perform(delete("/api/worlds/other")).andExpect(status().isNoContent());
        mvc.perform(delete("/api/worlds/missing")).andExpect(status().isNotFound());
        verify(store, never()).delete("current");
        verify(store).delete("other");
        verify(store).delete("missing");
    }
}
