package org.novelworld.world;

import java.util.ArrayList;
import java.util.Map;
import org.h2.jdbcx.JdbcDataSource;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import tools.jackson.databind.ObjectMapper;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
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
        var store = new WorldStore(jdbc, mock(StringRedisTemplate.class), new ObjectMapper());
        var service = new WorldTemplateService(store, new ObjectMapper());
        var original = service.defaultTemplate();
        var changed = service.defaultTemplate();
        ((Map<String, Object>) ((Map<String, Object>) changed.get("characters")).get("林默"))
                .put("goals", java.util.List.of("寻找遗失的信"));

        String firstId = service.createWorld(original);
        String secondId = service.createWorld(changed);
        assertEquals(2, store.listWorldIds().size());
        assertEquals(java.util.List.of("调查失踪案", "找到失踪者的下落"),
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
        assertEquals(java.util.List.of("调查失踪案", "找到失踪者的下落"),
                ((Map<?, ?>) ((Map<?, ?>) oldWorld.get("characters")).get("林默")).get("goals"));
        assertEquals(java.util.List.of("寻找遗失的信"),
                ((Map<?, ?>) ((Map<?, ?>) newWorld.get("characters")).get("林默")).get("goals"));
        assertTrue(((java.util.List<?>) newWorld.get("events")).isEmpty());
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
}
