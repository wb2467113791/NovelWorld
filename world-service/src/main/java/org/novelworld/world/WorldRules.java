package org.novelworld.world;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import org.springframework.stereotype.Component;

/** 只在这里结算真实活动与交流；模型意图不直接成为世界事实。 */
@Component
public class WorldRules {
    @SuppressWarnings("unchecked")
    static Map<String, Object> map(Object v) {
        if (!(v instanceof Map<?, ?>)) throw new IllegalArgumentException("需要对象数据");
        return (Map<String, Object>) v;
    }
    @SuppressWarnings("unchecked")
    static List<Object> list(Object v) {
        if (!(v instanceof List<?>)) throw new IllegalArgumentException("需要列表数据");
        return (List<Object>) v;
    }
    static String text(Map<String, Object> data, String key, int limit) {
        if (!(data.get(key) instanceof String s) || s.isBlank() || s.length() > limit)
            throw new IllegalArgumentException("文字参数无效：" + key);
        return s.trim();
    }
    static int number(Object v, int min, int max) {
        if (!(v instanceof Number n) || n.doubleValue() != n.intValue() || n.intValue() < min || n.intValue() > max)
            throw new IllegalArgumentException("整数必须在 " + min + " 到 " + max + " 之间");
        return n.intValue();
    }
    static String id() { return UUID.randomUUID().toString().replace("-", ""); }
    static int minute(Map<String, Object> w) { return number(w.get("minute"), 0, 100_000_000); }
    static Map<String, Object> actor(Map<String, Object> w, String name) {
        Object v = map(w.get("characters")).get(name);
        if (v == null) throw new IllegalArgumentException("角色不存在：" + name);
        return map(v);
    }
    static void requireCurrent(Map<String, Object> w) {
        if (!Integer.valueOf(3).equals(w.get("version")))
            throw new IllegalArgumentException("旧世界保留供导出；请创建社会沙盒新世界");
    }
    static List<String> nearby(Map<String, Object> w, String location) {
        var names = new ArrayList<String>();
        map(w.get("characters")).forEach((name, raw) -> { if (location.equals(map(raw).get("location"))) names.add(name); });
        return names;
    }
    static Map<String, Object> event(Map<String, Object> w, String type, String name, String target,
                                     String location, String description, Map<String, Object> payload, List<String> witnesses) {
        var e = new LinkedHashMap<String, Object>();
        e.put("id", id()); e.put("minute", minute(w)); e.put("time", w.get("time")); e.put("type", type);
        e.put("actor", name); e.put("target", target); e.put("location", location);
        e.put("description", description); e.put("payload", payload); e.put("perceived_by", new ArrayList<>(witnesses));
        list(w.get("events")).add(e);
        return e;
    }
    static Map<String, Object> conversation(Map<String, Object> w, String name) {
        return list(w.get("conversations")).stream().map(WorldRules::map)
                .filter(s -> list(s.get("participants")).contains(name)).findFirst().orElse(null);
    }
    private static void idle(Map<String, Object> w, String name) {
        if (actor(w, name).get("activity") != null) throw new IllegalArgumentException("正在活动；先 stop_activity 或等待完成");
        if (conversation(w, name) != null) throw new IllegalArgumentException("正在交谈；先 leave_conversation");
    }
    private static void stopActivity(Map<String, Object> w, String name) {
        var p = actor(w, name);
        if (p.get("activity") == null) throw new IllegalArgumentException("没有进行中的活动");
        var a = map(p.get("activity"));
        event(w, "activity_interrupted", name, null, (String) p.get("location"), name + "停下了" + a.get("name") + "。",
                new LinkedHashMap<>(a), nearby(w, (String) p.get("location")));
        p.put("activity", null);
    }
    private static void closeConversation(Map<String, Object> w, Map<String, Object> s, String reason) {
        var people = list(s.get("participants")).stream().map(Object::toString).toList();
        event(w, "conversation_ended", people.get(0), people.get(1), (String) s.get("location"),
                String.join("与", people) + "的交谈结束了（" + reason + "）。",
                Map.of("conversation_id", s.get("id"), "reason", reason), people);
        list(w.get("conversations")).remove(s);
    }
    /** 所有到期活动同时推进，角色无需获得模型轮次才能完成活动。 */
    public void advance(Map<String, Object> w) {
        requireCurrent(w);
        int now = minute(w) + 5;
        w.put("minute", now); w.put("tick_count", number(w.get("tick_count"), 0, 100_000_000) + 1);
        w.put("time", "第" + (now / 1440 + 1) + "天 " + String.format("%02d:%02d", now % 1440 / 60, now % 60));
        map(w.get("characters")).forEach((name, raw) -> {
            var p = map(raw);
            if (p.get("activity") != null) {
                var a = map(p.get("activity"));
                if (number(a.get("until"), 0, 100_000_000) <= now) {
                    event(w, "activity_completed", name, null, (String) p.get("location"), name + "结束了" + a.get("name") + "。",
                            new LinkedHashMap<>(a), nearby(w, (String) p.get("location")));
                    p.put("activity", null);
                }
            }
        });
        for (Object raw : new ArrayList<>(list(w.get("invitations")))) {
            var i = map(raw);
            if (number(i.get("expires"), 0, 100_000_000) <= now) {
                event(w, "invitation_expired", (String) i.get("from"), (String) i.get("to"), (String) i.get("location"),
                        i.get("from") + "向" + i.get("to") + "发出的交谈邀请未得到回应。", Map.of("invitation_id", i.get("id")),
                        List.of((String) i.get("from"), (String) i.get("to")));
                list(w.get("invitations")).remove(i);
            }
        }
        for (Object raw : new ArrayList<>(list(w.get("conversations")))) {
            var s = map(raw);
            if (now - number(s.get("last_minute"), 0, 100_000_000) >= 45) closeConversation(w, s, "暂时没有继续回应");
        }
    }
    public List<Object> apply(Map<String, Object> w, String name, String action, Map<String, Object> args) {
        requireCurrent(w);
        Set<String> fields = switch (action) {
            case "move" -> Set.of("location"); case "start_activity" -> Set.of("activity_id");
            case "invite" -> Set.of("target", "message"); case "respond_invitation" -> Set.of("invitation_id", "accept");
            case "say" -> Set.of("message"); case "inspect" -> Set.of("object_id");
            case "stop_activity", "leave_conversation", "wait" -> Set.of();
            default -> throw new IllegalArgumentException("未知行动：" + action);
        };
        if (!args.keySet().equals(fields)) throw new IllegalArgumentException("行动参数应为：" + fields);
        var p = actor(w, name); String location = (String) p.get("location"); int before = list(w.get("events")).size();
        switch (action) {
            case "move" -> {
                idle(w, name); String destination = text(args, "location", 80);
                if (!map(w.get("locations")).containsKey(destination) || destination.equals(location))
                    throw new IllegalArgumentException("目的地不存在或已在此处");
                var witnesses = nearby(w, location); p.put("location", destination);
                for (String witness : nearby(w, destination)) if (!witnesses.contains(witness)) witnesses.add(witness);
                event(w, "move", name, null, destination, name + "从" + location + "来到" + destination + "。",
                        Map.of("from", location, "to", destination), witnesses);
            }
            case "start_activity", "wait" -> {
                idle(w, name); Map<String, Object> definition; String activityId;
                if (action.equals("wait")) { activityId = "wait"; definition = Map.of("name", "静候片刻", "duration", 10); }
                else {
                    activityId = text(args, "activity_id", 80); Object raw = map(w.get("activities")).get(activityId);
                    if (raw == null) throw new IllegalArgumentException("活动不存在"); definition = map(raw);
                    if (!list(definition.get("locations")).contains(location)) throw new IllegalArgumentException("不在活动地点");
                    var roles = list(definition.get("roles"));
                    if (!roles.isEmpty() && !roles.contains(p.get("role"))) throw new IllegalArgumentException("身份不适合此活动");
                }
                var a = new LinkedHashMap<String, Object>(); a.put("id", activityId); a.put("name", definition.get("name"));
                a.put("started", minute(w)); a.put("until", minute(w) + number(definition.get("duration"), 5, 120)); p.put("activity", a);
                event(w, "activity_started", name, null, location, name + "开始" + definition.get("name") + "。", new LinkedHashMap<>(a), nearby(w, location));
            }
            case "stop_activity" -> stopActivity(w, name);
            case "invite" -> {
                idle(w, name); String target = text(args, "target", 80), message = text(args, "message", 600);
                var other = actor(w, target);
                if (name.equals(target) || !location.equals(other.get("location"))) throw new IllegalArgumentException("只能邀请同地点的另一人");
                if (conversation(w, target) != null) throw new IllegalArgumentException("对方正在与别人交谈");
                if (list(w.get("invitations")).stream().map(WorldRules::map).anyMatch(i -> name.equals(i.get("from"))
                        || (target.equals(i.get("from")) && name.equals(i.get("to")))))
                    throw new IllegalArgumentException("已有未处理的邀请，请等待或回应");
                var i = new LinkedHashMap<String, Object>(); i.put("id", id()); i.put("from", name); i.put("to", target);
                i.put("location", location); i.put("message", message); i.put("expires", minute(w) + 30); list(w.get("invitations")).add(i);
                event(w, "invitation", name, target, location, name + "向" + target + "招呼：“" + message + "”", new LinkedHashMap<>(i), List.of(name, target));
            }
            case "respond_invitation" -> {
                String invitationId = text(args, "invitation_id", 80);
                if (!(args.get("accept") instanceof Boolean)) throw new IllegalArgumentException("accept 必须是布尔值");
                var i = list(w.get("invitations")).stream().map(WorldRules::map)
                        .filter(v -> invitationId.equals(v.get("id")) && name.equals(v.get("to"))).findFirst()
                        .orElseThrow(() -> new IllegalArgumentException("没有属于本人的待回应邀请"));
                String from = (String) i.get("from"); boolean accepted = Boolean.TRUE.equals(args.get("accept"));
                if (accepted) {
                    if (!location.equals(actor(w, from).get("location")) || conversation(w, name) != null || conversation(w, from) != null
                            || actor(w, from).get("activity") != null) throw new IllegalArgumentException("双方需要同地点且邀请人空闲");
                    if (p.get("activity") != null) stopActivity(w, name);
                    var s = new LinkedHashMap<String, Object>(); s.put("id", id()); s.put("participants", List.of(from, name));
                    s.put("location", location); s.put("next_speaker", name); s.put("last_minute", minute(w)); s.put("messages", new ArrayList<>());
                    list(w.get("conversations")).add(s);
                }
                list(w.get("invitations")).remove(i);
                event(w, accepted ? "conversation_started" : "invitation_declined", name, from, location,
                        name + (accepted ? "接受了" : "婉拒了") + from + "的交谈邀请。", Map.of("invitation_id", invitationId), List.of(name, from));
            }
            case "say" -> {
                var s = conversation(w, name);
                if (s == null || !name.equals(s.get("next_speaker"))) throw new IllegalArgumentException("尚未轮到本人发言或没有会话");
                String message = text(args, "message", 1000);
                String target = list(s.get("participants")).stream().map(Object::toString).filter(v -> !name.equals(v)).findFirst().orElseThrow();
                var e = event(w, "talk", name, target, location, name + "对" + target + "说：“" + message + "”",
                        Map.of("conversation_id", s.get("id"), "message", message), List.of(name, target));
                list(s.get("messages")).add(Map.of("speaker", name, "message", message, "event_id", e.get("id")));
                s.put("next_speaker", target); s.put("last_minute", minute(w));
                if (list(s.get("messages")).size() >= 12) closeConversation(w, s, "本次交谈告一段落");
            }
            case "leave_conversation" -> {
                var s = conversation(w, name); if (s == null) throw new IllegalArgumentException("没有进行中的对话");
                closeConversation(w, s, name + "离开交谈");
            }
            case "inspect" -> {
                String objectId = text(args, "object_id", 80); Object raw = map(w.get("objects")).get(objectId);
                if (raw == null || !location.equals(map(raw).get("location"))) throw new IllegalArgumentException("对象不在本人现场");
                var o = map(raw);
                event(w, "inspect", name, null, location, name + "查看了" + o.get("name") + "：" + o.get("description"),
                        Map.of("object_id", objectId, "observation", o.get("description")), List.of(name));
            }
            default -> throw new IllegalArgumentException("无法执行行动");
        }
        return new ArrayList<>(list(w.get("events")).subList(before, list(w.get("events")).size()));
    }
}
