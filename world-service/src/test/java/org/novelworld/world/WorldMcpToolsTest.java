package org.novelworld.world;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.ObjectMapper;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class WorldMcpToolsTest {
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
        var tools = new WorldMcpTools(store, new WorldRules(new ObjectMapper()), new ObjectMapper());

        String json = tools.introduceWorldEvent("test-world", "stagnation", "晚风客栈", 3);

        assertTrue(json.contains("director"));
        assertEquals(1, ((List<?>) world.get("events")).size());
        assertFalse(((Map<?, ?>) ((Map<?, ?>) world.get("inspectable_objects")).get("晚风客栈")).isEmpty());
        assertEquals("晚风客栈", ((Map<?, ?>) ((Map<?, ?>) world.get("characters")).get("苏晚")).get("location"));
        verify(store).update(eq("test-world"), same(world));
        verify(store).queueEvent(eq("test-world"), anyMap());
    }
}
