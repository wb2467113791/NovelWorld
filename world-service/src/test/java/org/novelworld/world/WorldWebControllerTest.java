package org.novelworld.world;

import java.util.List;
import java.util.Map;
import java.util.Base64;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.ObjectMapper;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class WorldWebControllerTest {
    @Test void browserReadsJavaSnapshotWithoutPrivateSecrets() {
        var store = mock(WorldStore.class);
        var runtime = mock(AgentRuntimeClient.class);
        when(runtime.status()).thenReturn(Map.of("world_id", "w1", "tick_count", 2, "running", false, "error", ""));
        var person = Map.ofEntries(
                Map.entry("name", "苏晚"), Map.entry("role", "老板"), Map.entry("personality", "谨慎"),
                Map.entry("location", "客栈"), Map.entry("energy", 75),
                Map.entry("goals", List.of("保护弟弟")), Map.entry("items", List.of("账本")),
                Map.entry("relationships", Map.of("林默", 0)), Map.entry("known_facts", List.of("后门有人")),
                Map.entry("secrets", List.of("弟弟涉案")),
                Map.entry("memory", Map.of("entries", List.of(Map.of("content", "见过林默")), "archive", List.of())),
                Map.entry("semantic_memory", Map.of("facts", List.of(Map.of("observation", "门锁生锈")))));
        when(store.load("w1")).thenReturn(Map.of("world_id", "w1", "time", "08:10",
                "locations", List.of("客栈"), "characters", Map.of("苏晚", person), "events", List.of()));
        var controller = new WorldWebController(store, runtime, new ObjectMapper());

        assertEquals(75, ((Map<?, ?>) ((Map<?, ?>) controller.world().get("characters")).get("苏晚")).get("energy"));
        assertFalse(controller.world().toString().contains("弟弟涉案"));
        assertEquals(List.of("见过林默"), controller.characterView("苏晚").get("recent_memories"));
        assertFalse(controller.characterView("苏晚").toString().contains("弟弟涉案"));
        var mvc = org.springframework.test.web.servlet.setup.MockMvcBuilders.standaloneSetup(controller).build();
        assertDoesNotThrow(() -> mvc.perform(get("/api/world"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.characters.苏晚.energy").value(75)));
        var secured = org.springframework.test.web.servlet.setup.MockMvcBuilders.standaloneSetup(controller)
                .addFilters(new WebAccessFilter("author", "test-password")).build();
        assertDoesNotThrow(() -> secured.perform(get("/api/world")).andExpect(status().isUnauthorized()));
        String basic = Base64.getEncoder().encodeToString("author:test-password".getBytes(StandardCharsets.UTF_8));
        assertDoesNotThrow(() -> secured.perform(get("/api/world").header("Authorization", "Basic " + basic))
                .andExpect(status().isOk()));
        verify(store, atLeastOnce()).load("w1");
    }
}
