package org.novelworld.world;

import tools.jackson.core.JacksonException;
import tools.jackson.databind.ObjectMapper;
import java.util.List;
import java.util.Map;
import java.util.LinkedHashMap;
import java.util.UUID;
import org.springframework.ai.mcp.annotation.McpTool;
import org.springframework.ai.mcp.annotation.McpToolParam;
import org.springframework.stereotype.Component;

@Component
public class WorldMcpTools {
    private final WorldStore store;
    private final WorldRules rules;
    private final ObjectMapper mapper;

    public WorldMcpTools(WorldStore store, WorldRules rules, ObjectMapper mapper) {
        this.store = store; this.rules = rules; this.mapper = mapper;
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> parse(String json) {
        try { return mapper.readValue(json, Map.class); }
        catch (JacksonException e) { throw new IllegalArgumentException("JSON 格式无效", e); }
    }

    private String json(Object value) {
        try { return mapper.writeValueAsString(value); }
        catch (JacksonException e) { throw new IllegalArgumentException("状态无法序列化", e); }
    }

    @McpTool(name = "create_world", description = "从 V1.5 存档创建世界；相同 world_id 不可覆盖")
    public String createWorld(@McpToolParam(description = "完整世界 JSON 存档") String snapshotJson) {
        var snapshot = parse(snapshotJson);
        if (!Integer.valueOf(1).equals(snapshot.get("version"))) throw new IllegalArgumentException("存档版本不支持");
        String worldId = String.valueOf(snapshot.get("world_id"));
        if (worldId.isBlank() || "null".equals(worldId) || !(snapshot.get("characters") instanceof Map))
            throw new IllegalArgumentException("世界 ID 或角色缺失");
        snapshot.put("revision", 0);
        store.insert(worldId, snapshot);
        return worldId;
    }

    @McpTool(name = "get_world", description = "读取世界快照，包括地图、角色、物品、关系、时间、事件和存档")
    public String getWorld(@McpToolParam(description = "世界 ID") String worldId) {
        return json(store.load(worldId));
    }

    @McpTool(name = "get_world_events", description = "按事件序号读取已提交事件；返回下一游标")
    public String getWorldEvents(@McpToolParam(description = "世界 ID") String worldId,
                                 @McpToolParam(description = "已读取的事件数量") int afterIndex) {
        var events = (List<?>) store.load(worldId).get("events");
        if (afterIndex < 0 || afterIndex > events.size()) throw new IllegalArgumentException("事件游标无效");
        int end = Math.min(events.size(), afterIndex + 100);
        return json(Map.of("events", events.subList(afterIndex, end), "next_cursor", end));
    }

    /** 人只设定可观察的环境线索，不能指定 NPC 的下一步行动。 */
    @SuppressWarnings("unchecked")
    public synchronized Map<String, Object> injectWorldEvent(String worldId, String location,
                                                               String objectName, String observation) {
        if (objectName == null || objectName.isBlank() || observation == null || observation.isBlank()
                || objectName.length() > 80 || observation.length() > 1000)
            throw new IllegalArgumentException("线索名称或内容无效");
        var world = store.load(worldId);
        if (!((List<?>) world.get("locations")).contains(location)) throw new IllegalArgumentException("地点不存在：" + location);
        var objects = (Map<String, Object>) world.get("inspectable_objects");
        var place = (Map<String, Object>) objects.computeIfAbsent(location, ignored -> new LinkedHashMap<String, Object>());
        if (place.containsKey(objectName)) throw new IllegalArgumentException("该地点已有同名线索");
        place.put(objectName, observation);
        var event = new LinkedHashMap<String, Object>();
        event.put("id", UUID.randomUUID().toString().replace("-", ""));
        event.put("timestamp", world.get("time")); event.put("type", "intervention");
        event.put("actor", "世界"); event.put("target", null); event.put("location", location);
        event.put("perceived_by", WorldRules.perceivedBy(world, "director", "世界", null, location));
        event.put("payload", Map.of("object_name", objectName, "observation", observation));
        event.put("description", location + "出现了可调查的" + objectName + "。" + observation);
        ((List<Object>) world.get("events")).add(event);
        store.update(worldId, world);
        store.queueEvent(worldId, event);
        return event;
    }

    @McpTool(name = "execute_world_tool", description = "由 Java 校验并执行角色行动，返回结果及新增事件")
    public synchronized String executeWorldTool(
            @McpToolParam(description = "世界 ID") String worldId,
            @McpToolParam(description = "工具名") String name,
            @McpToolParam(description = "JSON 参数") String argumentsJson,
            @McpToolParam(description = "当前行动角色") String actingCharacter) {
        var world = store.load(worldId);
        var arguments = parse(argumentsJson);
        String actorKey = Map.of("get_character", "character", "inspect", "character", "talk", "speaker",
                "update_relationship", "character", "move_character", "character", "give_item", "giver",
                "rest_character", "character", "world_action", "actor").get(name);
        if (actorKey != null && !actingCharacter.equals(arguments.get(actorKey)))
            throw new IllegalArgumentException(actingCharacter + "不能通过" + name + "替其他角色行动");
        int before = ((List<?>) world.get("events")).size();
        String output = rules.apply(world, name, arguments);
        Object event = null;
        if (((List<?>) world.get("events")).size() != before) {
            event = ((List<?>) world.get("events")).get(before);
            store.update(worldId, world);
            store.queueEvent(worldId, (Map<String, Object>) event);
        }
        return json(Map.of("output", output, "event", event == null ? Map.of() : event, "revision", world.get("revision")));
    }

    @McpTool(name = "save_agent_state", description = "保存 Python 的记忆和 Tick 调度进度；不覆盖 Java 的世界业务状态")
    @SuppressWarnings("unchecked")
    public synchronized String saveAgentState(
            @McpToolParam(description = "世界 ID") String worldId,
            @McpToolParam(description = "各角色记忆和调度状态 JSON") String agentStateJson) {
        var world = store.load(worldId);
        var state = parse(agentStateJson);
        var characters = (Map<String, Object>) world.get("characters");
        var memories = (Map<String, Object>) state.get("characters");
        if (memories == null || !characters.keySet().equals(memories.keySet())) throw new IllegalArgumentException("角色集合不一致");
        for (var name : characters.keySet()) {
            var person = (Map<String, Object>) characters.get(name);
            var memory = (Map<String, Object>) memories.get(name);
            person.put("memory", memory.get("memory"));
            person.put("semantic_memory", memory.get("semantic_memory"));
        }
        world.put("scheduler", state.get("scheduler"));
        var existingEvents = (List<Map<String, Object>>) world.get("events");
        var suppliedEvents = (List<Map<String, Object>>) state.get("events");
        if (suppliedEvents != null) {
            var ids = existingEvents.stream().map(event -> event.get("id")).collect(java.util.stream.Collectors.toSet());
            for (var event : suppliedEvents) {
                if (!"narration".equals(event.get("type"))) throw new IllegalArgumentException("只能同步叙述事件");
                if (ids.add(event.get("id"))) existingEvents.add(event);
            }
        }
        store.update(worldId, world);
        return String.valueOf(world.get("revision"));
    }

    @McpTool(name = "introduce_world_event", description = "Director 只添加可调查的世界事件，不操纵 NPC 行为")
    @SuppressWarnings("unchecked")
    public synchronized String introduceWorldEvent(
            @McpToolParam(description = "世界 ID") String worldId,
            @McpToolParam(description = "stagnation、participation 或 conflict") String category,
            @McpToolParam(description = "事件发生的合法地点") String location,
            @McpToolParam(description = "触发事件的 Tick 数") int tickCount) {
        var observations = Map.of(
                "stagnation", "一张匿名纸条提到失踪案当晚的客栈后门；内容尚待核实。",
                "participation", "有人提及近期去向不明的货箱；传闻尚待核实。",
                "conflict", "县衙与商会互相质疑的告示被贴出；双方说法尚待核实。"
        );
        String observation = observations.get(category);
        if (observation == null) throw new IllegalArgumentException("未知 Director 事件类别");
        return introduceNarrativeEvent(worldId, category, location, observation, tickCount);
    }

    @McpTool(name = "introduce_narrative_event", description = "由规则触发的 Director 提议环境线索，Java 校验并结算")
    @SuppressWarnings("unchecked")
    public synchronized String introduceNarrativeEvent(
            @McpToolParam(description = "世界 ID") String worldId,
            @McpToolParam(description = "stagnation、participation 或 conflict") String category,
            @McpToolParam(description = "事件发生的合法地点") String location,
            @McpToolParam(description = "新的可调查线索内容") String observation,
            @McpToolParam(description = "触发事件的 Tick 数") int tickCount) {
        if (!List.of("stagnation", "participation", "conflict").contains(category))
            throw new IllegalArgumentException("未知 Director 事件类别");
        if (observation == null || observation.isBlank() || observation.length() > 1000)
            throw new IllegalArgumentException("Director 线索内容无效");
        if (tickCount < 1) throw new IllegalArgumentException("Tick 数无效");
        var world = store.load(worldId);
        if (!((List<?>) world.get("locations")).contains(location)) throw new IllegalArgumentException("地点不存在：" + location);
        var objects = (Map<String, Object>) world.get("inspectable_objects");
        var place = (Map<String, Object>) objects.computeIfAbsent(location, ignored -> new LinkedHashMap<String, Object>());
        int sequence = ((List<?>) world.get("events")).size() + 1;
        while (place.containsKey("新线索" + sequence)) sequence++;
        String objectName = "新线索" + sequence;
        place.put(objectName, observation);
        var event = new LinkedHashMap<String, Object>();
        event.put("id", UUID.randomUUID().toString().replace("-", ""));
        event.put("timestamp", world.get("time")); event.put("type", "director");
        event.put("actor", "世界"); event.put("target", null); event.put("location", location);
        event.put("perceived_by", WorldRules.perceivedBy(world, "director", "世界", null, location));
        event.put("payload", Map.of("category", category, "object_name", objectName, "observation", observation, "tick_count", tickCount));
        event.put("description", location + "出现了可调查的" + objectName + "。" + observation);
        ((List<Object>) world.get("events")).add(event);
        store.update(worldId, world);
        store.queueEvent(worldId, event);
        return json(event);
    }

    @McpTool(name = "advance_world_time", description = "由 Java 推进世界时钟并持久化")
    public synchronized String advanceWorldTime(
            @McpToolParam(description = "世界 ID") String worldId,
            @McpToolParam(description = "推进的分钟数") int minutes) {
        if (minutes < 1) throw new IllegalArgumentException("推进分钟数必须至少为 1");
        var world = store.load(worldId);
        String[] parts = ((String) world.get("time")).split(":");
        int total = (Integer.parseInt(parts[0]) * 60 + Integer.parseInt(parts[1]) + minutes) % 1440;
        String time = String.format("%02d:%02d", total / 60, total % 60);
        world.put("time", time);
        store.update(worldId, world);
        return time;
    }
}
