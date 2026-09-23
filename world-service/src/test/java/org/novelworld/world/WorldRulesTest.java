package org.novelworld.world;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.ObjectMapper;

import static org.junit.jupiter.api.Assertions.*;

class WorldRulesTest {
    private final WorldRules rules = new WorldRules(new ObjectMapper());

    private Map<String, Object> world() {
        var lin = new HashMap<String, Object>();
        lin.put("name", "林默"); lin.put("role", "捕快"); lin.put("location", "县衙");
        lin.put("energy", 90); lin.put("items", new ArrayList<>(List.of("腰牌")));
        lin.put("relationships", new HashMap<>(Map.of("苏晚", 0)));
        var su = new HashMap<String, Object>();
        su.put("name", "苏晚"); su.put("role", "老板"); su.put("location", "客栈");
        su.put("energy", 80); su.put("items", new ArrayList<>(List.of("账本")));
        su.put("relationships", new HashMap<>(Map.of("林默", 0)));
        var world = new HashMap<String, Object>();
        world.put("characters", Map.of("林默", lin, "苏晚", su));
        world.put("locations", List.of("县衙", "客栈"));
        world.put("inspectables", Map.of("客栈", "整洁"));
        world.put("inspectable_objects", Map.of("客栈", Map.of("账簿", "空白")));
        world.put("events", new ArrayList<>()); world.put("time", "08:00");
        return world;
    }

    @Test void movementAndEventAreReal() {
        var world = world();
        assertThrows(IllegalArgumentException.class, () -> rules.apply(world, "move_character", Map.of("character", "林默", "location", "远山")));
        assertEquals(0, ((List<?>) world.get("events")).size());
        rules.apply(world, "move_character", Map.of("character", "林默", "location", "客栈"));
        assertEquals("客栈", ((Map<?, ?>) ((Map<?, ?>) world.get("characters")).get("林默")).get("location"));
        assertEquals(1, ((List<?>) world.get("events")).size());
    }

    @Test void inventoryRequiresOwnershipAndColocation() {
        var world = world();
        assertThrows(IllegalArgumentException.class, () -> rules.apply(world, "give_item", Map.of("giver", "苏晚", "receiver", "林默", "item", "账本")));
        rules.apply(world, "move_character", Map.of("character", "林默", "location", "客栈"));
        rules.apply(world, "give_item", Map.of("giver", "苏晚", "receiver", "林默", "item", "账本"));
        assertTrue(((List<?>) ((Map<?, ?>) ((Map<?, ?>) world.get("characters")).get("林默")).get("items")).contains("账本"));
        assertThrows(IllegalArgumentException.class, () -> rules.apply(world, "give_item", Map.of("giver", "苏晚", "receiver", "林默", "item", "账本")));
    }

    @Test void repeatedInspectionDoesNotCreateEvent() {
        var world = world();
        rules.apply(world, "inspect", Map.of("character", "苏晚", "object_name", "账簿"));
        assertThrows(IllegalArgumentException.class, () -> rules.apply(world, "inspect", Map.of("character", "苏晚", "object_name", "账簿")));
        assertEquals(1, ((List<?>) world.get("events")).size());
    }

    @Test void speechCannotInventAnInspection() {
        var world = world();
        rules.apply(world, "move_character", Map.of("character", "林默", "location", "客栈"));
        assertThrows(IllegalArgumentException.class, () -> rules.apply(world, "talk", Map.of(
                "speaker", "林默", "listener", "苏晚", "message", "我看过账簿。")));
        rules.apply(world, "inspect", Map.of("character", "林默", "object_name", "账簿"));
        assertDoesNotThrow(() -> rules.apply(world, "talk", Map.of(
                "speaker", "林默", "listener", "苏晚", "message", "我看过账簿。")));
    }

    @Test void energyCostsAndRestAreEnforcedWithoutPartialMutation() {
        var world = world();
        var lin = (Map<String, Object>) ((Map<?, ?>) world.get("characters")).get("林默");
        rules.apply(world, "move_character", Map.of("character", "林默", "location", "客栈"));
        assertEquals(85, lin.get("energy"));
        lin.put("energy", 2);
        int events = ((List<?>) world.get("events")).size();
        assertThrows(IllegalArgumentException.class, () -> rules.apply(world, "move_character", Map.of("character", "林默", "location", "县衙")));
        assertEquals("客栈", lin.get("location"));
        assertEquals(2, lin.get("energy"));
        assertEquals(events, ((List<?>) world.get("events")).size());
        rules.apply(world, "rest_character", Map.of("character", "林默"));
        assertEquals(22, lin.get("energy"));
        lin.put("energy", 95);
        rules.apply(world, "rest_character", Map.of("character", "林默"));
        assertEquals(100, lin.get("energy"));
        assertThrows(IllegalArgumentException.class, () -> rules.apply(world, "rest_character", Map.of("character", "林默")));
    }
}
