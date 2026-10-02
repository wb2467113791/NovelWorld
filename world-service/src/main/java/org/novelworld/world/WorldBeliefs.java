package org.novelworld.world;

import java.util.*;

/** 校验 NPC 认知来源，绝不用于世界行为结算。 */
final class WorldBeliefs {
    private WorldBeliefs() {}

    private static String text(Object raw) {
        if (!(raw instanceof String value) || value.isBlank()) throw new IllegalArgumentException("Belief 文字字段无效");
        return value;
    }
    private static String normalized(String value) { return value.replaceAll("(?U)\\s+", " ").trim(); }
    private static boolean visible(Map<?, ?> event, String owner) {
        if (event.get("perceived_by") instanceof List<?> witnesses) return witnesses.contains(owner);
        return owner.equals(event.get("actor")) || owner.equals(event.get("target")); // 旧事件只信直接参与者。
    }

    static void validate(Object raw, String owner, Map<String, Object> world) {
        var person = WorldObjects.map(WorldObjects.map(world.get("characters")).get(owner));
        if (person == null || !WorldActors.isNpc(person)) throw new IllegalArgumentException("Belief 只属于 NPC");
        if (!(raw instanceof Map<?, ?> memory) || !Set.of("entries").equals(memory.keySet())
                || !(memory.get("entries") instanceof List<?> entries) || entries.size() > 50)
            throw new IllegalArgumentException("BeliefMemory 字段或数量无效");
        var events = WorldObjects.list(world.get("events"));
        var committed = new HashMap<String, Map<String, Object>>();
        var positions = new HashMap<String, Integer>();
        for (int index = 0; index < events.size(); index++) {
            var event = WorldObjects.map(events.get(index));
            committed.put((String) event.get("id"), event); positions.put((String) event.get("id"), index);
        }
        var ids = new HashSet<String>(); var keys = new HashSet<List<String>>();
        for (Object item : entries) {
            if (!(item instanceof Map<?, ?> entry) || !Set.of("id", "owner", "content", "source_type", "source_actor",
                    "source_event_id", "confidence", "status", "order", "evidence_event_ids").equals(entry.keySet()))
                throw new IllegalArgumentException("BeliefEntry 字段无效");
            String id = text(entry.get("id")), content = text(entry.get("content"));
            String type = text(entry.get("source_type")), actor = text(entry.get("source_actor"));
            if (!owner.equals(entry.get("owner")) || !ids.add(id) || !keys.add(List.of(type, actor, normalized(content)))
                    || !"active".equals(entry.get("status")) || !Set.of("report", "initial").contains(type))
                throw new IllegalArgumentException("Belief 归属、重复或类型无效");
            if (!(entry.get("confidence") instanceof Number confidence) || !Double.isFinite(confidence.doubleValue())
                    || confidence.doubleValue() != ("report".equals(type) ? 0.5 : 1.0))
                throw new IllegalArgumentException("Belief confidence 必须由程序确定");
            Object rawOrder = entry.get("order");
            if (!(rawOrder instanceof Integer || rawOrder instanceof Long) || ((Number) rawOrder).longValue() < 0
                    || !(entry.get("evidence_event_ids") instanceof List<?> evidence))
                throw new IllegalArgumentException("Belief order / evidence 无效");
            long order = ((Number) rawOrder).longValue();
            if ("initial".equals(type)) {
                if (!owner.equals(actor) || entry.get("source_event_id") != null || !evidence.isEmpty() || order != 0
                        || !((List<?>) person.get("known_facts")).contains(content))
                    throw new IllegalArgumentException("Initial Belief 必须来自本人开局设定");
                continue;
            }
            if (evidence.isEmpty() || evidence.size() > 5 || new HashSet<>(evidence).size() != evidence.size()
                    || !Objects.equals(entry.get("source_event_id"), evidence.get(evidence.size() - 1)))
                throw new IllegalArgumentException("Report evidence 无效");
            int previous = -1;
            for (Object source : evidence) {
                var event = committed.get(text(source));
                if (event == null || !"talk".equals(event.get("type")) || !actor.equals(event.get("actor"))
                        || owner.equals(actor) || !visible(event, owner)
                        || !normalized(content).equals(normalized(text(WorldObjects.map(event.get("payload")).get("message"))))
                        || positions.get(source) <= previous)
                    throw new IllegalArgumentException("Report 必须来自本人可见的真实 talk");
                previous = positions.get(source);
            }
            if (order != previous) throw new IllegalArgumentException("Report order 必须匹配最新证据");
        }
    }
}
