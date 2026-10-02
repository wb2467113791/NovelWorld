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
        if (!Integer.valueOf(1).equals(snapshot.get("version")) && !Integer.valueOf(2).equals(snapshot.get("version"))) throw new IllegalArgumentException("存档版本不支持");
        String worldId = String.valueOf(snapshot.get("world_id"));
        if (worldId.isBlank() || "null".equals(worldId) || !(snapshot.get("characters") instanceof Map))
            throw new IllegalArgumentException("世界 ID 或角色缺失");
        snapshot.put("revision", 0);
        if (snapshot.containsKey("active_conversations"))
            validateConversations(snapshot.get("active_conversations"), snapshot);
        WorldObjects.map(snapshot.get("characters")).forEach((name, raw) -> {
            var person = WorldObjects.map(raw);
            if (person.containsKey("belief_memory")) WorldBeliefs.validate(person.get("belief_memory"), name, snapshot);
        });
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
        WorldObjects.ensure(world);
        var objects = WorldObjects.map(world.get("objects"));
        if (objects.values().stream().map(WorldObjects::map).anyMatch(item -> objectName.equals(item.get("name"))
                && location.equals(WorldObjects.location(world, item))))
            throw new IllegalArgumentException("该地点已有同名对象");
        var object = WorldObjects.sceneObject(location, objectName, observation);
        if (((Map<?, ?>) world.get("objects")).containsKey(object.get("id")))
            throw new IllegalArgumentException("该线索已存在，不能覆盖其物理状态");
        ((Map<String, Object>) world.get("objects")).put((String) object.get("id"), object);
        WorldObjects.projectInventory(world);
        var event = new LinkedHashMap<String, Object>();
        event.put("id", UUID.randomUUID().toString().replace("-", ""));
        event.put("timestamp", world.get("time")); event.put("type", "intervention");
        event.put("actor", "世界"); event.put("target", null); event.put("location", location);
        event.put("perceived_by", WorldRules.perceivedBy(world, "director", "世界", null, location));
        event.put("payload", Map.of("object_name", objectName, "observation", observation));
        event.put("description", location + "出现了可调查的" + objectName + "。" + observation);
        ((List<Object>) world.get("events")).add(event);
        store.update(worldId, world);
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
        String actorKey = switch (name) {
            case "talk" -> "speaker";
            case "world_action" -> "actor";
            case "inspect", "take", "put", "give", "use", "interact", "move_character",
                    "rest_character" -> "character";
            default -> null;
        };
        if (actorKey != null && !actingCharacter.equals(arguments.get(actorKey)))
            throw new IllegalArgumentException(actingCharacter + "不能通过" + name + "替其他角色行动");
        var actingActor = WorldObjects.map(WorldObjects.map(world.get("characters")).get(actingCharacter));
        if (actingActor == null) throw new IllegalArgumentException("角色不存在：" + actingCharacter);
        if (!WorldActors.isNpc(actingActor) && !java.util.Set.of("inspect", "take", "put", "give", "use",
                "interact", "move_character", "talk", "rest_character").contains(name)
                && !("world_action".equals(name) && "attack".equals(arguments.get("action"))))
            throw new IllegalArgumentException("Player 不支持该工具");
        int before = ((List<?>) world.get("events")).size();
        String output = rules.apply(world, name, arguments);
        Object event = null;
        if (((List<?>) world.get("events")).size() != before) {
            event = ((List<?>) world.get("events")).get(before);
            store.update(worldId, world);
        }
        return json(Map.of("output", output, "event", event == null ? Map.of() : event, "revision", world.get("revision")));
    }

    @McpTool(name = "save_agent_state", description = "保存 Python 的记忆、角色认知和 Tick 调度进度；不覆盖 Java 的世界业务状态")
    @SuppressWarnings("unchecked")
    public synchronized String saveAgentState(
            @McpToolParam(description = "世界 ID") String worldId,
            @McpToolParam(description = "各角色记忆和调度状态 JSON") String agentStateJson) {
        var world = store.load(worldId);
        var state = parse(agentStateJson);
        var characters = (Map<String, Object>) world.get("characters");
        var memories = (Map<String, Object>) state.get("characters");
        // 旧客户端的空 events 可兼容；任何新事件只能由 Java 世界行动产生。
        if (state.containsKey("events") && (!(state.get("events") instanceof List<?> events) || !events.isEmpty()))
            throw new IllegalArgumentException("Agent 状态保存不能创建世界事件");
        var npcNames = characters.entrySet().stream().filter(entry -> WorldActors.isNpc(WorldObjects.map(entry.getValue())))
                .map(Map.Entry::getKey).collect(java.util.stream.Collectors.toSet());
        if (memories == null || !npcNames.equals(memories.keySet())) throw new IllegalArgumentException("NPC 角色集合不一致");
        if (state.containsKey("active_conversations"))
            validateConversations(state.get("active_conversations"), world);
        // 先验证所有角色的认知；意图不是世界事实，不能夹带业务字段或其他角色的 Agenda。
        for (var name : npcNames) {
            var memory = (Map<String, Object>) memories.get(name);
            if (memory.containsKey("runtime_state"))
                validateRuntime(memory.get("runtime_state"), name, (Map<String, Object>) characters.get(name));
            if (memory.containsKey("belief_memory"))
                WorldBeliefs.validate(memory.get("belief_memory"), name, world);
        }
        for (var name : npcNames) {
            var person = (Map<String, Object>) characters.get(name);
            var memory = (Map<String, Object>) memories.get(name);
            person.put("memory", memory.get("memory"));
            person.put("semantic_memory", memory.get("semantic_memory"));
            if (memory.containsKey("runtime_state")) person.put("runtime_state", memory.get("runtime_state"));
            if (memory.containsKey("belief_memory")) person.put("belief_memory", memory.get("belief_memory"));
        }
        world.put("scheduler", state.get("scheduler"));
        if (state.containsKey("active_conversations")) world.put("active_conversations", state.get("active_conversations"));
        store.update(worldId, world);
        return String.valueOf(world.get("revision"));
    }

    private static void validateRuntime(Object raw, String owner, Map<String, Object> person) {
        if (!(raw instanceof Map<?, ?> runtime) || !java.util.Set.of(
                "active_goal", "current_intention", "current_plan", "agenda", "busy_until").containsAll(runtime.keySet()))
            throw new IllegalArgumentException("Agent runtime 字段无效");
        for (String field : List.of("active_goal", "current_intention", "current_plan")) {
            Object value = runtime.get(field);
            if (value != null && (!(value instanceof String text) || text.isBlank()))
                throw new IllegalArgumentException(field + " 必须是非空文字");
        }
        Object goal = runtime.get("active_goal");
        if (goal != null && !((List<?>) person.get("goals")).contains(goal))
            throw new IllegalArgumentException("active_goal 必须来自本人目标");
        validateTick(runtime.get("busy_until"), true);
        Object agendaValue = runtime.getOrDefault("agenda", null);
        if (agendaValue == null && !runtime.containsKey("agenda")) return;
        if (!(agendaValue instanceof List<?> agenda)) throw new IllegalArgumentException("Agenda 必须是列表");
        var ids = new java.util.HashSet<String>();
        for (Object item : agenda) {
            if (!(item instanceof Map<?, ?> entry) || !java.util.Set.of(
                    "id", "character", "due_tick", "intention", "status").containsAll(entry.keySet()))
                throw new IllegalArgumentException("Agenda 字段无效");
            for (String field : List.of("id", "character", "intention")) {
                if (!(entry.get(field) instanceof String text) || text.isBlank())
                    throw new IllegalArgumentException("Agenda 文字字段无效");
            }
            if (!owner.equals(entry.get("character")) || !ids.add((String) entry.get("id")))
                throw new IllegalArgumentException("Agenda 归属或 ID 无效");
            validateTick(entry.get("due_tick"), false);
            Object status = entry.containsKey("status") ? entry.get("status") : "pending";
            if (!List.of("pending", "completed", "cancelled").contains(status))
                throw new IllegalArgumentException("Agenda status 无效");
        }
    }

    private static void validateTick(Object value, boolean nullable) {
        if (value == null && nullable) return;
        if (!(value instanceof Integer || value instanceof Long) || ((Number) value).longValue() < 0)
            throw new IllegalArgumentException("时间必须是非负累计 Tick 序号");
    }

    /** 内部 runtime 可维护会话，但不能伪造说话事实；每条消息必须对应本世界已提交 talk。 */
    private static void validateConversations(Object raw, Map<String, Object> world) {
        if (!(raw instanceof List<?> sessions)) throw new IllegalArgumentException("Conversation 必须是列表");
        var characters = (Map<?, ?>) world.get("characters");
        var events = (List<?>) world.get("events");
        var committed = new java.util.HashMap<Object, Map<?, ?>>();
        var positions = new java.util.HashMap<Object, Integer>();
        for (int index = 0; index < events.size(); index++) {
            var event = (Map<?, ?>) events.get(index);
            committed.put(event.get("id"), event); positions.put(event.get("id"), index);
        }
        var ids = new java.util.HashSet<Object>();
        var participants = new java.util.HashSet<Object>();
        var messageIds = new java.util.HashSet<Object>();
        for (var item : sessions) {
            if (!(item instanceof Map<?, ?> session) || !java.util.Set.of("id", "participants", "location", "status",
                    "messages", "started_tick", "last_activity_tick", "next_speaker").equals(session.keySet()))
                throw new IllegalArgumentException("Conversation 字段无效");
            if (!(session.get("id") instanceof String id) || id.isBlank() || !ids.add(id)
                    || !"active".equals(session.get("status"))) throw new IllegalArgumentException("Conversation ID / status 无效");
            if (!(session.get("participants") instanceof List<?> names) || names.size() != 2
                    || !characters.keySet().containsAll(names) || names.get(0).equals(names.get(1))
                    || !names.contains(session.get("next_speaker"))) throw new IllegalArgumentException("Conversation participants 无效");
            for (Object name : names) if (!participants.add(name))
                throw new IllegalArgumentException("角色不能同时参与多个 active Conversation");
            if (!((List<?>) world.get("locations")).contains(session.get("location")))
                throw new IllegalArgumentException("Conversation location 无效");
            validateTick(session.get("started_tick"), false); validateTick(session.get("last_activity_tick"), false);
            long started = ((Number) session.get("started_tick")).longValue();
            long previousTick = started;
            int previousPosition = -1;
            if (!(session.get("messages") instanceof List<?> messages) || messages.isEmpty() || messages.size() > 12)
                throw new IllegalArgumentException("Conversation messages 数量无效");
            Map<?, ?> lastEvent = null;
            for (int index = 0; index < messages.size(); index++) {
                if (!(messages.get(index) instanceof Map<?, ?> message) || !java.util.Set.of("speaker", "content", "tick", "event_id").equals(message.keySet()))
                    throw new IllegalArgumentException("Conversation message 字段无效");
                validateTick(message.get("tick"), false);
                long tick = ((Number) message.get("tick")).longValue();
                var event = committed.get(message.get("event_id"));
                if (event == null || !messageIds.add(message.get("event_id")) || !"talk".equals(event.get("type"))
                        || !names.contains(event.get("actor")) || !names.contains(event.get("target"))
                        || event.get("actor").equals(event.get("target")) || !event.get("actor").equals(message.get("speaker"))
                        || !event.get("location").equals(session.get("location"))
                        || !((Map<?, ?>) event.get("payload")).get("message").equals(message.get("content"))
                        || !(event.get("perceived_by") instanceof List<?> witnesses) || !witnesses.containsAll(names)
                        || tick < previousTick || (index == 0 && tick != started)
                        || positions.get(message.get("event_id")) <= previousPosition)
                    throw new IllegalArgumentException("Conversation message 必须匹配真实 talk event 和顺序");
                previousTick = tick; previousPosition = positions.get(message.get("event_id")); lastEvent = event;
            }
            if (((Number) session.get("last_activity_tick")).longValue() != previousTick
                    || !lastEvent.get("target").equals(session.get("next_speaker")))
                throw new IllegalArgumentException("Conversation 时间或轮次无效");
        }
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
        WorldObjects.ensure(world);
        var objects = WorldObjects.map(world.get("objects"));
        int sequence = ((List<?>) world.get("events")).size() + 1;
        while (objects.containsKey(WorldObjects.stableId("scene\0" + location + "\0新线索" + sequence))) sequence++;
        String objectName = "新线索" + sequence;
        var object = WorldObjects.sceneObject(location, objectName, observation);
        if (((Map<?, ?>) world.get("objects")).containsKey(object.get("id")))
            throw new IllegalArgumentException("该线索已存在，不能覆盖其物理状态");
        ((Map<String, Object>) world.get("objects")).put((String) object.get("id"), object);
        WorldObjects.projectInventory(world);
        var event = new LinkedHashMap<String, Object>();
        event.put("id", UUID.randomUUID().toString().replace("-", ""));
        event.put("timestamp", world.get("time")); event.put("type", "director");
        event.put("actor", "世界"); event.put("target", null); event.put("location", location);
        event.put("perceived_by", WorldRules.perceivedBy(world, "director", "世界", null, location));
        event.put("payload", Map.of("category", category, "object_name", objectName, "observation", observation, "tick_count", tickCount));
        event.put("description", location + "出现了可调查的" + objectName + "。" + observation);
        ((List<Object>) world.get("events")).add(event);
        store.update(worldId, world);
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
