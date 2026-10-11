package org.novelworld.world;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.springframework.ai.mcp.annotation.McpTool;
import org.springframework.ai.mcp.annotation.McpToolParam;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;
import tools.jackson.databind.ObjectMapper;

/** 一次角色轮次原子提交行动与认知；Java 自己生成真实事件和故事记录的关联。 */
@Component
public class WorldMcpTools {
    private final WorldStore store;
    private final WorldRules rules;
    private final WorldTemplateService templates;
    private final ObjectMapper mapper;
    public WorldMcpTools(WorldStore store, WorldRules rules, WorldTemplateService templates, ObjectMapper mapper) {
        this.store = store; this.rules = rules; this.templates = templates; this.mapper = mapper;
    }
    @SuppressWarnings("unchecked")
    private Map<String, Object> parse(String json) { return mapper.readValue(json, Map.class); }
    private String json(Object value) { return mapper.writeValueAsString(value); }

    @McpTool(name = "get_world", description = "读取完整权威快照，仅内部 Runtime 使用")
    public String getWorld(@McpToolParam(description = "世界ID") String worldId) { return json(store.load(worldId)); }

    @McpTool(name = "initialize_world", description = "首次启动创建新的社会沙盒；不修改旧世界")
    public synchronized String initializeWorld() {
        String id = templates.createWorld(templates.defaultTemplate()); return json(store.load(id));
    }
    @McpTool(name = "advance_world", description = "推进5分钟并结算所有活动；expectedTick 避免重放时间推进")
    public synchronized String advanceWorld(@McpToolParam(description = "世界ID") String worldId,
                                            @McpToolParam(description = "推进前Tick") int expectedTick) {
        var w = store.load(worldId); WorldRules.requireCurrent(w);
        int tick = WorldRules.number(w.get("tick_count"), 0, 100_000_000);
        if (tick == expectedTick + 1) return json(w);
        if (tick != expectedTick) throw new IllegalArgumentException("Tick 已改变，请重新同步");
        rules.advance(w); store.update(worldId, w); return json(w);
    }

    @McpTool(name = "get_execution", description = "内部 Runtime 按请求ID确认持久提交状态；不执行行动")
    public String getExecution(String worldId, String actor, String requestId) {
        store.load(worldId); // 兼容迁移旧 v3 存档的现存回执
        var receipt = store.execution(worldId, requestId);
        if (receipt == null) return json(Map.of("status", "not_committed"));
        if (!actor.equals(receipt.get("actor"))) throw new IllegalArgumentException("请求不属于本人");
        var feedback = new LinkedHashMap<String, Object>(receipt); feedback.remove("request_hash");
        return json(feedback);
    }

    @McpTool(name = "move", description = "空闲且不在会话时移动到已有地点；校验并原子保存行动与认知")
    @Transactional
    public synchronized String performMove(@McpToolParam(description = "世界ID") String worldId,
            @McpToolParam(description = "行动者，由Runtime绑定") String actor,
            @McpToolParam(description = "幂等请求ID，由Runtime绑定") String requestId,
            @McpToolParam(description = "观察时revision") long expectedRevision,
            @McpToolParam(description = "简短行动动机") String reason,
            @McpToolParam(description = "内部JSON: mind, memories；由Runtime组装") String cognitionJson,
            @McpToolParam(description = "location") String location) {
        return execute(worldId, actor, requestId, expectedRevision, "move", Map.of("location", location), reason, cognitionJson);
    }

    @McpTool(name = "invite", description = "邀请现场另一人交谈；校验并原子保存行动与认知")
    @Transactional
    public synchronized String performInvite(@McpToolParam(description = "世界ID") String worldId,
            @McpToolParam(description = "行动者，由Runtime绑定") String actor,
            @McpToolParam(description = "幂等请求ID，由Runtime绑定") String requestId,
            @McpToolParam(description = "观察时revision") long expectedRevision,
            @McpToolParam(description = "简短行动动机") String reason,
            @McpToolParam(description = "内部JSON: mind, memories；由Runtime组装") String cognitionJson,
            @McpToolParam(description = "target") String target,
            @McpToolParam(description = "message") String message) {
        return execute(worldId, actor, requestId, expectedRevision, "invite", Map.of("target", target, "message", message), reason, cognitionJson);
    }

    @McpTool(name = "say", description = "在本人会话轮次发言；校验并原子保存行动与认知")
    @Transactional
    public synchronized String performSay(@McpToolParam(description = "世界ID") String worldId,
            @McpToolParam(description = "行动者，由Runtime绑定") String actor,
            @McpToolParam(description = "幂等请求ID，由Runtime绑定") String requestId,
            @McpToolParam(description = "观察时revision") long expectedRevision,
            @McpToolParam(description = "简短行动动机") String reason,
            @McpToolParam(description = "内部JSON: mind, memories；由Runtime组装") String cognitionJson,
            @McpToolParam(description = "message") String message) {
        return execute(worldId, actor, requestId, expectedRevision, "say", Map.of("message", message), reason, cognitionJson);
    }

    @McpTool(name = "inspect", description = "查看本人现场对象；校验并原子保存行动与认知")
    @Transactional
    public synchronized String performInspect(@McpToolParam(description = "世界ID") String worldId,
            @McpToolParam(description = "行动者，由Runtime绑定") String actor,
            @McpToolParam(description = "幂等请求ID，由Runtime绑定") String requestId,
            @McpToolParam(description = "观察时revision") long expectedRevision,
            @McpToolParam(description = "简短行动动机") String reason,
            @McpToolParam(description = "内部JSON: mind, memories；由Runtime组装") String cognitionJson,
            @McpToolParam(description = "object_id") String object_id) {
        return execute(worldId, actor, requestId, expectedRevision, "inspect", Map.of("object_id", object_id), reason, cognitionJson);
    }

    @McpTool(name = "start_activity", description = "开始符合地点与身份的持续活动；校验并原子保存行动与认知")
    @Transactional
    public synchronized String performStartActivity(@McpToolParam(description = "世界ID") String worldId,
            @McpToolParam(description = "行动者，由Runtime绑定") String actor,
            @McpToolParam(description = "幂等请求ID，由Runtime绑定") String requestId,
            @McpToolParam(description = "观察时revision") long expectedRevision,
            @McpToolParam(description = "简短行动动机") String reason,
            @McpToolParam(description = "内部JSON: mind, memories；由Runtime组装") String cognitionJson,
            @McpToolParam(description = "activity_id") String activity_id) {
        return execute(worldId, actor, requestId, expectedRevision, "start_activity", Map.of("activity_id", activity_id), reason, cognitionJson);
    }

    @McpTool(name = "stop_activity", description = "中断本人活动；校验并原子保存行动与认知")
    @Transactional
    public synchronized String performStopActivity(@McpToolParam(description = "世界ID") String worldId,
            @McpToolParam(description = "行动者，由Runtime绑定") String actor,
            @McpToolParam(description = "幂等请求ID，由Runtime绑定") String requestId,
            @McpToolParam(description = "观察时revision") long expectedRevision,
            @McpToolParam(description = "简短行动动机") String reason,
            @McpToolParam(description = "内部JSON: mind, memories；由Runtime组装") String cognitionJson) {
        return execute(worldId, actor, requestId, expectedRevision, "stop_activity", Map.of(), reason, cognitionJson);
    }

    @McpTool(name = "respond_invitation", description = "接受或拒绝本人收到的邀请；校验并原子保存行动与认知")
    @Transactional
    public synchronized String performRespondInvitation(@McpToolParam(description = "世界ID") String worldId,
            @McpToolParam(description = "行动者，由Runtime绑定") String actor,
            @McpToolParam(description = "幂等请求ID，由Runtime绑定") String requestId,
            @McpToolParam(description = "观察时revision") long expectedRevision,
            @McpToolParam(description = "简短行动动机") String reason,
            @McpToolParam(description = "内部JSON: mind, memories；由Runtime组装") String cognitionJson,
            @McpToolParam(description = "invitation_id") String invitation_id,
            @McpToolParam(description = "accept") boolean accept) {
        return execute(worldId, actor, requestId, expectedRevision, "respond_invitation", Map.of("invitation_id", invitation_id, "accept", accept), reason, cognitionJson);
    }

    @McpTool(name = "leave_conversation", description = "结束本人会话；校验并原子保存行动与认知")
    @Transactional
    public synchronized String performLeaveConversation(@McpToolParam(description = "世界ID") String worldId,
            @McpToolParam(description = "行动者，由Runtime绑定") String actor,
            @McpToolParam(description = "幂等请求ID，由Runtime绑定") String requestId,
            @McpToolParam(description = "观察时revision") long expectedRevision,
            @McpToolParam(description = "简短行动动机") String reason,
            @McpToolParam(description = "内部JSON: mind, memories；由Runtime组装") String cognitionJson) {
        return execute(worldId, actor, requestId, expectedRevision, "leave_conversation", Map.of(), reason, cognitionJson);
    }

    @McpTool(name = "wait", description = "静候10分钟，占用活动时间；校验并原子保存行动与认知")
    @Transactional
    public synchronized String performWait(@McpToolParam(description = "世界ID") String worldId,
            @McpToolParam(description = "行动者，由Runtime绑定") String actor,
            @McpToolParam(description = "幂等请求ID，由Runtime绑定") String requestId,
            @McpToolParam(description = "观察时revision") long expectedRevision,
            @McpToolParam(description = "简短行动动机") String reason,
            @McpToolParam(description = "内部JSON: mind, memories；由Runtime组装") String cognitionJson) {
        return execute(worldId, actor, requestId, expectedRevision, "wait", Map.of(), reason, cognitionJson);
    }

    private String execute(String worldId, String actor, String requestId, long expectedRevision,
                           String action, Map<String, Object> arguments, String reason, String cognitionJson) {
        try {
            return executeValidated(worldId, actor, requestId, expectedRevision, action, arguments, reason, cognitionJson);
        } catch (IllegalArgumentException error) {
            // 只有明确的规则/输入拒绝允许模型改选。存储等系统异常交由客户端确认提交状态。
            return json(Map.of("status", "rejected", "error", error.getMessage()));
        }
    }
    private String executeValidated(String worldId, String actor, String requestId, long expectedRevision,
                                    String action, Map<String, Object> arguments, String reason, String cognitionJson) {
        var w = store.load(worldId); WorldRules.requireCurrent(w);
        if (requestId == null || !requestId.matches("[a-zA-Z0-9-]{1,80}")) throw new IllegalArgumentException("请求ID无效");
        var cognition = parse(cognitionJson);
        if (!cognition.keySet().equals(Set.of("mind", "memories"))) throw new IllegalArgumentException("认知封装字段无效");
        var turn = new LinkedHashMap<String, Object>(cognition);
        turn.put("action", action); turn.put("arguments", arguments); turn.put("reason", reason);
        var request = new LinkedHashMap<String, Object>(turn);
        request.put("actor", actor); request.put("expected_revision", expectedRevision);
        String requestHash = requestHash(request);
        var previous = store.execution(worldId, requestId);
        if (previous != null) {
            if (!actor.equals(previous.get("actor")) || !action.equals(previous.get("action"))
                    || (previous.containsKey("request_hash") && !requestHash.equals(previous.get("request_hash"))))
                throw new IllegalArgumentException("请求ID已用于不同的行动或内容");
            var feedback = new LinkedHashMap<String, Object>(previous); feedback.remove("request_hash");
            return json(Map.of("world", w, "execution", feedback));
        }
        if (((Number) w.get("revision")).longValue() != expectedRevision) throw new IllegalArgumentException("世界已改变，请重新观察");
        WorldRules.text(turn, "reason", 600);
        var person = WorldRules.actor(w, actor);
        boolean npc = "npc".equals(person.get("actor_type"));
        if (npc) validateCognition(w, actor, WorldRules.map(turn.get("mind")), WorldRules.list(turn.get("memories")));
        else if (!WorldRules.map(turn.get("mind")).isEmpty() || !WorldRules.list(turn.get("memories")).isEmpty())
            throw new IllegalArgumentException("玩家不能提交NPC认知");
        var committed = rules.apply(w, actor, action, WorldRules.map(turn.get("arguments")));
        if (npc) {
            var mind = WorldRules.map(turn.get("mind")); var memories = WorldRules.list(turn.get("memories"));
            // 把本轮真实结果直接追加为亲历，避免重启时丢失最后一次行动的记忆。
            for (Object raw : committed) {
                var e = WorldRules.map(raw);
                memories.add(Map.of("id", e.get("id"), "kind", "observation", "content", "亲历：" + e.get("description"),
                        "minute", w.get("minute"), "importance", "talk".equals(e.get("type")) ? 4 : 2,
                        "source_event_ids", List.of(e.get("id"))));
            }
            mind.put("event_cursor", WorldRules.list(w.get("events")).size());
            person.put("mind", mind); person.put("memories", memories);
        }
        var d = new LinkedHashMap<String, Object>(); d.put("id", requestId); d.put("actor", actor);
        d.put("minute", w.get("minute")); d.put("time", w.get("time")); d.put("location", person.get("location"));
        d.put("reason", reason); d.put("action", action);
        d.put("intention", npc ? WorldRules.map(turn.get("mind")).getOrDefault("intention", "") : "玩家输入");
        d.put("goal", npc ? WorldRules.map(turn.get("mind")).getOrDefault("goal", "") : "");
        d.put("event_ids", committed.stream().map(e -> WorldRules.map(e).get("id")).toList());
        d.put("status", "committed");
        // 最后一条事件展示动机，全部真实事件通过 request_id 关联同一个提交。
        for (Object raw : committed) WorldRules.map(raw).put("request_id", requestId);
        WorldRules.map(committed.get(committed.size() - 1)).put("action_trace", new LinkedHashMap<>(d));
        d.put("request_hash", requestHash);
        store.update(worldId, w);
        store.saveExecution(worldId, requestId, d);
        var feedback = new LinkedHashMap<String, Object>(d); feedback.remove("request_hash");
        return json(Map.of("world", w, "execution", feedback));
    }
    private Object canonical(Object value) {
        if (value instanceof Map<?, ?> m) {
            var sorted = new java.util.TreeMap<String, Object>();
            m.forEach((key, item) -> sorted.put(key.toString(), canonical(item)));
            return sorted;
        }
        if (value instanceof List<?> items) return items.stream().map(this::canonical).toList();
        return value;
    }
    private String requestHash(Map<String, Object> request) {
        try {
            return java.util.HexFormat.of().formatHex(java.security.MessageDigest.getInstance("SHA-256")
                    .digest(json(canonical(request)).getBytes(java.nio.charset.StandardCharsets.UTF_8)));
        } catch (java.security.NoSuchAlgorithmException error) { throw new IllegalStateException(error); }
    }
    /** 来源引用必须属于本人的真实可见经历。关系文字是本人印象，不是客观心理或数值。 */
    private static void validateCognition(Map<String, Object> w, String name, Map<String, Object> mind, List<Object> memories) {
        if (!Set.of("goal", "intention", "plan", "reflection", "relationship_notes", "last_decision", "next_decision", "event_cursor", "reflection_cursor").equals(mind.keySet()))
            throw new IllegalArgumentException("认知字段无效");
        for (String key : List.of("goal", "intention", "reflection")) {
            if (!(mind.get(key) instanceof String s) || s.length() > 600) throw new IllegalArgumentException("认知文字过长");
        }
        var plans = WorldRules.list(mind.get("plan"));
        if (plans.size() > 6) throw new IllegalArgumentException("最多6条粗粒度计划");
        for (Object raw : plans) {
            var p = WorldRules.map(raw);
            if (!p.keySet().equals(Set.of("at", "location", "purpose")) || !WorldRules.map(w.get("locations")).containsKey(p.get("location")))
                throw new IllegalArgumentException("计划字段或地点无效");
            WorldRules.number(p.get("at"), 0, 100_000_000); WorldRules.text(p, "purpose", 250);
        }
        WorldRules.number(mind.get("last_decision"), WorldRules.minute(w), WorldRules.minute(w));
        WorldRules.number(mind.get("next_decision"), WorldRules.minute(w), WorldRules.minute(w) + 120);
        WorldRules.number(mind.get("event_cursor"), 0, WorldRules.list(w.get("events")).size());
        WorldRules.number(mind.get("reflection_cursor"), 0, memories.size());
        var notes = WorldRules.map(mind.get("relationship_notes"));
        notes.forEach((target, value) -> {
            if (!WorldRules.map(w.get("characters")).containsKey(target) || name.equals(target) || !(value instanceof String s) || s.length() > 500)
                throw new IllegalArgumentException("关系印象字段无效");
        });
        var visibleIds = new java.util.HashSet<Object>();
        for (Object raw : WorldRules.list(w.get("events"))) {
            var e = WorldRules.map(raw);
            if (WorldRules.list(e.get("perceived_by")).contains(name)) visibleIds.add(e.get("id"));
        }
        var ids = new java.util.HashSet<Object>();
        for (Object raw : memories) {
            var m = WorldRules.map(raw);
            if (!m.keySet().equals(Set.of("id", "kind", "content", "minute", "importance", "source_event_ids"))
                    || !ids.add(m.get("id"))) throw new IllegalArgumentException("记忆字段或ID无效");
            WorldRules.text(m, "id", 80); WorldRules.text(m, "content", 2000);
            WorldRules.number(m.get("minute"), 0, WorldRules.minute(w)); WorldRules.number(m.get("importance"), 1, 5);
            if (!List.of("observation", "reported", "reflection").contains(m.get("kind"))) throw new IllegalArgumentException("记忆类型无效");
            var sources = WorldRules.list(m.get("source_event_ids"));
            if (sources.isEmpty() || !visibleIds.containsAll(sources)) throw new IllegalArgumentException("记忆必须来自本人可见的真实事件");
        }
    }
    @McpTool(name = "join_player", description = "加入一个没有自主认知的玩家；不能冒用NPC身份")
    public synchronized String joinPlayer(@McpToolParam(description = "世界ID") String worldId,
                                          @McpToolParam(description = "玩家姓名") String name,
                                          @McpToolParam(description = "起始地点") String location) {
        var w = store.load(worldId); WorldRules.requireCurrent(w);
        if (name == null || name.isBlank() || name.length() > 40) throw new IllegalArgumentException("玩家名字无效");
        var people = WorldRules.map(w.get("characters"));
        if (people.values().stream().map(WorldRules::map).anyMatch(p -> "player".equals(p.get("actor_type")))) return json(w);
        if (people.containsKey(name) || !WorldRules.map(w.get("locations")).containsKey(location)) throw new IllegalArgumentException("姓名已占用或地点无效");
        var p = new LinkedHashMap<String, Object>(); p.put("name", name); p.put("role", "旅人"); p.put("actor_type", "player");
        p.put("location", location); p.put("activity", null); people.put(name, p);
        WorldRules.event(w, "arrival", name, null, location, name + "来到了小镇。", Map.of(), WorldRules.nearby(w, location));
        store.update(worldId, w); return json(w);
    }
}
