package org.novelworld.world;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

/** 同一权威角色集合中的单个人类角色；旧存档确定性迁移。 */
final class WorldActors {
    private WorldActors() {}

    static boolean isNpc(Map<?, ?> actor) {
        return "npc".equals(actor.containsKey("actor_type") ? actor.get("actor_type") : "npc");
    }

    static Map<String, Object> player(Map<String, Object> world) {
        return WorldObjects.map(world.get("characters")).values().stream().map(WorldObjects::map)
                .filter(actor -> "player".equals(actor.get("actor_type"))).findFirst().orElseThrow();
    }

    static void ensure(Map<String, Object> world) { ensure(world, null); }

    static void ensure(Map<String, Object> world, Map<String, Object> configured) {
        var actors = WorldObjects.map(world.get("characters"));
        var locations = (List<?>) world.get("locations");
        int players = 0;
        for (var entry : actors.entrySet()) {
            var actor = WorldObjects.map(entry.getValue());
            Object type = actor.getOrDefault("actor_type", "npc");
            if (!List.of("npc", "player").contains(type)) throw new IllegalArgumentException("actor_type 无效");
            actor.put("actor_type", type);
            if (!"player".equals(type)) continue;
            players++;
            if (entry.getKey().isBlank() || !entry.getKey().equals(actor.get("name")) || !locations.contains(actor.get("location")))
                throw new IllegalArgumentException("Player 姓名或地点无效");
            for (String field : List.of("energy", "hp")) {
                Object value = actor.get(field);
                if (!(value instanceof Number number) || number.doubleValue() != number.intValue()
                        || number.intValue() < 0 || number.intValue() > 100)
                    throw new IllegalArgumentException("Player " + field + " 无效");
            }
            if (!List.of("normal", "unconscious").contains(actor.get("status"))
                    || !(actor.get("relationships") instanceof Map) || !(actor.get("items") instanceof List)
                    || !Set.of("name", "location", "energy", "hp", "status", "items", "relationships", "actor_type")
                    .containsAll(actor.keySet())) throw new IllegalArgumentException("Player 字段无效");
        }
        if (players > 1) throw new IllegalArgumentException("每个世界仅支持一个 Player");
        if (players == 1) return;
        String name = "玩家";
        Object location = locations.get(0);
        if (configured != null) {
            if (!Set.of("name", "location").containsAll(configured.keySet())
                    || !(configured.get("name") instanceof String text) || text.isBlank()
                    || !locations.contains(configured.get("location"))) throw new IllegalArgumentException("player 模板无效");
            name = (String) configured.get("name");
            location = configured.get("location");
            if (actors.containsKey(name)) throw new IllegalArgumentException("Player 与 NPC 姓名冲突");
        } else {
            int suffix = 2;
            while (actors.containsKey(name)) name = "玩家" + suffix++;
        }
        var player = new LinkedHashMap<String, Object>();
        player.put("name", name); player.put("location", location); player.put("actor_type", "player");
        player.put("energy", 100); player.put("hp", 100); player.put("status", "normal");
        player.put("items", new ArrayList<>()); player.put("relationships", new LinkedHashMap<>());
        actors.put(name, player);
    }
}
