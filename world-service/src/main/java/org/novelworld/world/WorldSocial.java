package org.novelworld.world;

import java.util.List;
import java.util.Map;

/** 只评价已通过校验的真实互动，在原行动快照提交之前结算。 */
final class WorldSocial {
    private WorldSocial() {}

    static void apply(Map<String, Object> world, Map<String, Object> event) {
        int requested = switch ((String) event.get("type")) {
            case "give" -> 2;
            case "attack" -> -15;
            default -> 0;
        };
        if (requested == 0) return;
        String owner = (String) event.get("target"), target = (String) event.get("actor");
        var person = WorldObjects.map(WorldObjects.map(world.get("characters")).get(owner));
        var relationships = WorldObjects.map(person.get("relationships"));
        int before = ((Number) relationships.getOrDefault(target, 0)).intValue();
        int after = Math.max(-100, Math.min(100, before + requested));
        relationships.put(target, after);
        WorldObjects.map(event.get("payload")).put("relationship_changes", List.of(Map.of(
                "owner", owner, "target", target, "delta", after - before,
                "before", before, "after", after)));
    }
}
