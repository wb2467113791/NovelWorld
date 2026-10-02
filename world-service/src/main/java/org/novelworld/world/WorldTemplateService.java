package org.novelworld.world;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.springframework.stereotype.Service;
import tools.jackson.databind.ObjectMapper;

@Service
public class WorldTemplateService {
    private final WorldStore store;
    private final ObjectMapper mapper;
    public WorldTemplateService(WorldStore store, ObjectMapper mapper) { this.store = store; this.mapper = mapper; }
    @SuppressWarnings("unchecked")
    public Map<String, Object> defaultTemplate() {
        try (var stream = getClass().getResourceAsStream("/default-world-template.json")) { return mapper.readValue(stream, Map.class); }
        catch (Exception error) { throw new IllegalStateException("默认世界读取失败", error); }
    }
    public String createWorld(Map<String, Object> template) {
        if (!template.keySet().equals(Set.of("title", "premise", "locations", "characters", "activities", "objects", "lore")))
            throw new IllegalArgumentException("开局字段不完整或含旧格式字段");
        WorldRules.text(template, "title", 80); WorldRules.text(template, "premise", 1500);
        var locations = WorldRules.map(template.get("locations"));
        if (locations.isEmpty() || locations.size() > 8) throw new IllegalArgumentException("需要1到8个地点");
        locations.forEach((name, raw) -> {
            if (name.isBlank() || name.length() > 80 || !(raw instanceof String s) || s.isBlank() || s.length() > 1000)
                throw new IllegalArgumentException("地点描述无效");
        });
        var characters = WorldRules.map(template.get("characters"));
        if (characters.size() < 2 || characters.size() > 6) throw new IllegalArgumentException("需要2到6个 NPC");
        var w = new LinkedHashMap<String, Object>(template); w.put("version", 3); w.put("world_id", WorldRules.id());
        w.put("minute", 480); w.put("time", "第1天 08:00"); w.put("tick_count", 0); w.put("revision", 0);
        var people = new LinkedHashMap<String, Object>();
        characters.forEach((name, raw) -> {
            var p = new LinkedHashMap<>(WorldRules.map(raw));
            if (!p.keySet().equals(Set.of("role", "background", "personality", "goals", "secrets", "relationships", "location", "skills")))
                throw new IllegalArgumentException("角色设定字段无效：" + name);
            if (name.isBlank() || name.length() > 80) throw new IllegalArgumentException("角色名无效");
            for (String f : List.of("role", "background", "personality")) WorldRules.text(p, f, 1500);
            if (!locations.containsKey(p.get("location"))) throw new IllegalArgumentException("角色地点无效");
            for (String f : List.of("goals", "secrets", "skills")) {
                var entries = WorldRules.list(p.get(f));
                if (entries.size() > 8 || entries.stream().anyMatch(v -> !(v instanceof String s) || s.isBlank() || s.length() > 600))
                    throw new IllegalArgumentException("角色文字列表无效：" + f);
            }
            for (Object skill : WorldRules.list(p.get("skills")))
                if (!List.of("hospitality", "community", "craft", "social").contains(skill)) throw new IllegalArgumentException("未知 Skill");
            WorldRules.map(p.get("relationships")).forEach((target, value) -> {
                if (!characters.containsKey(target) || name.equals(target) || !(value instanceof String s) || s.length() > 500)
                    throw new IllegalArgumentException("关系应是对已存在人物的主观描述");
            });
            p.put("name", name); p.put("actor_type", "npc"); p.put("activity", null);
            p.put("mind", new LinkedHashMap<>()); p.put("memories", new ArrayList<>()); people.put(name, p);
        });
        WorldRules.map(template.get("activities")).forEach((id, raw) -> {
            var a = WorldRules.map(raw);
            if (!a.keySet().equals(Set.of("name", "locations", "roles", "duration"))) throw new IllegalArgumentException("活动字段无效");
            WorldRules.text(a, "name", 80); WorldRules.number(a.get("duration"), 5, 120);
            if (WorldRules.list(a.get("locations")).isEmpty() || !locations.keySet().containsAll(WorldRules.list(a.get("locations"))))
                throw new IllegalArgumentException("活动地点无效");
            if (WorldRules.list(a.get("roles")).stream().anyMatch(r -> !(r instanceof String))) throw new IllegalArgumentException("活动身份无效");
        });
        WorldRules.map(template.get("objects")).forEach((id, raw) -> {
            var o = WorldRules.map(raw);
            if (!o.keySet().equals(Set.of("name", "location", "description")) || !locations.containsKey(o.get("location")))
                throw new IllegalArgumentException("对象字段或地点无效");
            WorldRules.text(o, "name", 80); WorldRules.text(o, "description", 1500);
        });
        for (Object raw : WorldRules.list(template.get("lore"))) {
            var l = WorldRules.map(raw);
            if (!l.keySet().equals(Set.of("id", "text", "audience"))) throw new IllegalArgumentException("设定字段无效");
            WorldRules.text(l, "id", 80); WorldRules.text(l, "text", 1500);
            if (!"public".equals(l.get("audience")) && !characters.containsKey(l.get("audience"))) throw new IllegalArgumentException("设定可见范围无效");
        }
        w.put("characters", people);
        for (String f : List.of("events", "invitations", "conversations", "decisions")) w.put(f, new ArrayList<>());
        store.insert((String) w.get("world_id"), w); return (String) w.get("world_id");
    }
}
