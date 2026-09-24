package org.novelworld.world;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import org.springframework.core.io.ClassPathResource;
import org.springframework.stereotype.Service;
import tools.jackson.databind.ObjectMapper;

/** 开局模板只描述初始条件；记忆、事件和世界 ID 在创建时生成。 */
@Service
public class WorldTemplateService {
    private static final List<String> CHARACTER_FIELDS = List.of(
            "name", "role", "background", "personality", "goals", "location", "energy",
            "secrets", "known_facts", "relationships", "items");
    private final WorldStore store;
    private final ObjectMapper mapper;

    public WorldTemplateService(WorldStore store, ObjectMapper mapper) {
        this.store = store;
        this.mapper = mapper;
    }

    @SuppressWarnings("unchecked")
    public Map<String, Object> defaultTemplate() {
        try (var input = new ClassPathResource("default-world-template.json").getInputStream()) {
            return mapper.readValue(new String(input.readAllBytes(), StandardCharsets.UTF_8), Map.class);
        } catch (IOException error) {
            throw new IllegalStateException("无法读取默认开局模板", error);
        }
    }

    public String createWorld(Map<String, Object> template) {
        validate(template);
        var world = new LinkedHashMap<String, Object>();
        String worldId = UUID.randomUUID().toString().replace("-", "");
        world.put("version", 1);
        world.put("world_id", worldId);
        world.put("revision", 0);
        world.put("time", template.get("time"));
        world.put("locations", copy(template.get("locations")));
        world.put("inspectables", copy(template.get("inspectables")));
        world.put("inspectable_objects", copy(template.get("inspectable_objects")));
        world.put("lore", copy(template.getOrDefault("lore", List.of())));
        world.put("events", new ArrayList<>());
        var characters = new LinkedHashMap<String, Object>();
        map(template.get("characters"), "characters").forEach((name, raw) -> {
            var source = map(raw, "角色 " + name);
            var character = new LinkedHashMap<String, Object>();
            for (String field : CHARACTER_FIELDS) character.put(field, copy(source.get(field)));
            character.put("hp", 100);
            character.put("status", "normal");
            character.put("memory", Map.of("max_items", 5, "entries", List.of(),
                    "archive", List.of(), "reflection_cursor", 0));
            character.put("semantic_memory", Map.of("facts", List.of(), "superseded_event_ids", List.of()));
            characters.put(name, character);
        });
        world.put("characters", characters);
        world.put("scheduler", Map.of("next_index", 0, "tick_count", 0));
        store.insert(worldId, world);
        return worldId;
    }

    private Object copy(Object value) {
        return mapper.readValue(mapper.writeValueAsString(value), Object.class);
    }

    private static void validate(Map<String, Object> template) {
        if (template == null) throw new IllegalArgumentException("开局模板不能为空");
        String time = text(template.get("time"), "time");
        if (!time.matches("(?:[01][0-9]|2[0-3]):[0-5][0-9]"))
            throw new IllegalArgumentException("世界时间必须是 HH:mm");

        var locations = textList(template.get("locations"), "locations", true);
        var locationSet = new HashSet<>(locations);
        if (locationSet.size() != locations.size()) throw new IllegalArgumentException("地点名称不能重复");
        var inspectables = map(template.get("inspectables"), "inspectables");
        for (String location : locations)
            text(inspectables.get(location), "地点描述 " + location);
        if (!locationSet.containsAll(inspectables.keySet()))
            throw new IllegalArgumentException("地点描述引用了不存在的地点");
        var objects = map(template.get("inspectable_objects"), "inspectable_objects");
        for (var place : objects.entrySet()) {
            if (!locationSet.contains(place.getKey()))
                throw new IllegalArgumentException("线索引用了不存在的地点：" + place.getKey());
            for (var object : map(place.getValue(), "地点线索 " + place.getKey()).entrySet()) {
                text(object.getKey(), "线索名称");
                text(object.getValue(), "线索内容");
            }
        }

        var characters = map(template.get("characters"), "characters");
        if (characters.isEmpty()) throw new IllegalArgumentException("至少需要一名 NPC");
        Set<String> ownedItems = new HashSet<>();
        for (var entry : characters.entrySet()) {
            String name = text(entry.getKey(), "角色标识");
            var character = map(entry.getValue(), "角色 " + name);
            if (!name.equals(text(character.get("name"), "角色姓名")))
                throw new IllegalArgumentException("角色标识与姓名不一致：" + name);
            for (String field : List.of("role", "background", "personality"))
                text(character.get(field), name + " 的 " + field);
            textList(character.get("goals"), name + " 的 goals", true);
            textList(character.get("secrets"), name + " 的 secrets", false);
            textList(character.get("known_facts"), name + " 的 known_facts", false);
            String location = text(character.get("location"), name + " 的 location");
            if (!locationSet.contains(location)) throw new IllegalArgumentException(name + " 的地点不存在：" + location);
            Object energy = character.get("energy");
            if (!(energy instanceof Number number) || number.intValue() != number.doubleValue()
                    || number.intValue() < 0 || number.intValue() > 100)
                throw new IllegalArgumentException(name + " 的体力必须在 0 到 100 之间");
            for (String item : textList(character.get("items"), name + " 的 items", false))
                if (!ownedItems.add(item)) throw new IllegalArgumentException("物品重复归属：" + item);
            for (var relation : map(character.get("relationships"), name + " 的 relationships").entrySet()) {
                if (name.equals(relation.getKey()) || !characters.containsKey(relation.getKey()))
                    throw new IllegalArgumentException(name + " 的关系对象无效：" + relation.getKey());
                Object score = relation.getValue();
                if (!(score instanceof Number relationNumber) || relationNumber.intValue() != relationNumber.doubleValue()
                        || relationNumber.intValue() < -100 || relationNumber.intValue() > 100)
                    throw new IllegalArgumentException(name + " 的关系值必须在 -100 到 100 之间");
            }
        }
        var loreIds = new HashSet<String>();
        for (Object raw : list(template.getOrDefault("lore", List.of()), "lore")) {
            var entry = map(raw, "世界设定");
            String id = text(entry.get("id"), "世界设定 ID");
            if (!loreIds.add(id)) throw new IllegalArgumentException("世界设定 ID 不能重复：" + id);
            text(entry.get("category"), "世界设定类别");
            text(entry.get("text"), "世界设定内容");
            String audience = text(entry.get("audience"), "世界设定可见者");
            if (!"public".equals(audience) && !characters.containsKey(audience))
                throw new IllegalArgumentException("世界设定引用了不存在的角色：" + audience);
        }
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> map(Object value, String field) {
        if (!(value instanceof Map<?, ?> raw)) throw new IllegalArgumentException(field + " 必须是对象");
        for (Object key : raw.keySet()) text(key, field + " 的键");
        return (Map<String, Object>) raw;
    }

    private static String text(Object value, String field) {
        if (!(value instanceof String result) || result.isBlank())
            throw new IllegalArgumentException(field + " 不能为空");
        return result;
    }

    private static List<String> textList(Object value, String field, boolean nonempty) {
        var raw = list(value, field);
        if (nonempty && raw.isEmpty()) throw new IllegalArgumentException(field + " 必须是非空列表");
        var result = new ArrayList<String>();
        for (Object item : raw) result.add(text(item, field + " 的内容"));
        return result;
    }

    private static List<?> list(Object value, String field) {
        if (!(value instanceof List<?> raw)) throw new IllegalArgumentException(field + " 必须是列表");
        return raw;
    }
}
