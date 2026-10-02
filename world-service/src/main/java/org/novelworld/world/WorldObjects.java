package org.novelworld.world;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.*;

/** 小型对象模型与明确的基础动作；不存在脚本、registry 或第二套 inventory。 */
final class WorldObjects {
    private WorldObjects() {}
    static final Set<String> TOOLS = Set.of("inspect", "take", "put", "give", "use", "interact", "give_item", "conceal_clue", "recover_clue");
    static final Set<String> ACTIONS = Set.of("open", "close", "light", "extinguish", "consume");
    static final Set<String> PROPERTIES = Set.of("container", "heal", "legacy_concealable", "trace_for", "hidden_at_index");
    @SuppressWarnings("unchecked") static Map<String, Object> map(Object value) { return (Map<String, Object>) value; }
    @SuppressWarnings("unchecked") static List<Object> list(Object value) { return (List<Object>) value; }
    static String text(Object value) {
        if (!(value instanceof String result) || result.isBlank()) throw new IllegalArgumentException("对象参数必须是非空文字");
        return result;
    }
    static String stableId(String origin) {
        try { return "obj-" + HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(origin.getBytes(StandardCharsets.UTF_8))).substring(0, 24); }
        catch (java.security.NoSuchAlgorithmException error) { throw new IllegalStateException(error); }
    }
    static Map<String, Object> object(String id, String name, String location, String description) {
        var result = new LinkedHashMap<String, Object>();
        result.put("id", id); result.put("name", name); result.put("type", "item"); result.put("description", description);
        result.put("location", location); result.put("container", null); result.put("holder", null); result.put("owner", null);
        result.put("portable", true); result.put("visible", true); result.put("state", "normal");
        result.put("properties", new LinkedHashMap<String, Object>()); result.put("affordances", new ArrayList<String>());
        return result;
    }
    static Map<String, Object> sceneObject(String location, String name, String description) {
        var result = object(stableId("scene\0" + location + "\0" + name), name, location, description);
        // 仅旧默认场景迁移的明确映射；运行中的 use 不再根据物品名称推断用途。
        if (Set.of("后门", "木箱", "柴房门锁").contains(name)) {
            result.put("portable", false);
            result.put("type", "木箱".equals(name) ? "container" : "door"); result.put("state", "closed");
            result.put("affordances", new ArrayList<>(List.of("open", "close")));
            if ("木箱".equals(name)) map(result.get("properties")).put("container", true);
        }
        return result;
    }
    static void ensure(Map<String, Object> world) {
        if (!world.containsKey("objects")) {
            var objects = new LinkedHashMap<String, Object>();
            var allowed = map(world.getOrDefault("concealable_objects", Map.of()));
            map(world.getOrDefault("inspectable_objects", Map.of())).forEach((place, raw) -> map(raw).forEach((name, observation) -> {
                var item = sceneObject(place, name, text(observation));
                if (((List<?>) allowed.getOrDefault(place, List.of())).contains(name)) map(item.get("properties")).put("legacy_concealable", true);
                objects.put((String) item.get("id"), item);
            }));
            map(world.getOrDefault("concealed_objects", Map.of())).forEach((place, raw) -> map(raw).forEach((name, hidden) -> {
                var old = map(hidden); var item = sceneObject(place, name, text(old.get("observation")));
                item.put("visible", false); map(item.get("properties")).put("legacy_concealable", true);
                map(item.get("properties")).put("hidden_at_index", old.getOrDefault("concealed_at_event_count", 0));
                objects.put((String) item.get("id"), item);
                var trace = map(objects.get(stableId("scene\0" + place + "\0" + old.get("trace_name"))));
                if (trace != null) {
                    trace.put("portable", false);
                    map(trace.get("properties")).put("trace_for", item.get("id"));
                    map(trace.get("properties")).put("hidden_at_index", old.getOrDefault("concealed_at_event_count", 0));
                }
            }));
            map(world.get("characters")).forEach((name, raw) -> {
                for (Object label : (List<?>) map(raw).getOrDefault("items", List.of())) {
                    var item = object(stableId("inventory\0" + name + "\0" + label), text(label), null, "一件" + label + "。");
                    item.put("holder", name); item.put("owner", name);
                    if (((String) label).contains("药")) {
                        item.put("affordances", new ArrayList<>(List.of("consume"))); map(item.get("properties")).put("heal", 20);
                    }
                    if (objects.putIfAbsent((String) item.get("id"), item) != null) throw new IllegalArgumentException("旧物品重复");
                }
            });
            world.put("objects", objects);
        }
        validate(world); project(world);
    }
    static void validate(Map<String, Object> world) {
        if (!(world.get("objects") instanceof Map<?, ?>)) throw new IllegalArgumentException("objects 必须按 ID 保存");
        var objects = map(world.get("objects")); var characters = map(world.get("characters"));
        for (var entry : objects.entrySet()) {
            if (!(entry.getValue() instanceof Map<?, ?>)) throw new IllegalArgumentException("World Object 字段无效");
            var item = map(entry.getValue());
            if (!Set.of("id", "name", "type", "description", "location", "container", "holder", "owner", "portable", "visible", "state", "properties", "affordances").equals(item.keySet()))
                throw new IllegalArgumentException("World Object 字段无效");
            for (String field : List.of("id", "name", "type", "description", "state")) text(item.get(field));
            if (!entry.getKey().equals(item.get("id")) || !(item.get("portable") instanceof Boolean) || !(item.get("visible") instanceof Boolean))
                throw new IllegalArgumentException("Object ID 或布尔字段无效");
            if (!Set.of("normal", "open", "closed", "locked", "lit", "extinguished", "damaged", "consumed").contains(item.get("state")))
                throw new IllegalArgumentException("Object state 无效");
            if (!(item.get("properties") instanceof Map<?, ?> properties) || !PROPERTIES.containsAll(properties.keySet())
                    || !(item.get("affordances") instanceof List<?> affordances) || !ACTIONS.containsAll(affordances))
                throw new IllegalArgumentException("Object properties / affordances 无效");
            for (String field : List.of("container", "legacy_concealable")) if (properties.containsKey(field) && !(properties.get(field) instanceof Boolean))
                throw new IllegalArgumentException("Object property 必须是布尔值");
            for (String field : List.of("heal", "hidden_at_index")) if (properties.containsKey(field) && (!(properties.get(field) instanceof Integer n) || n < 0 || ("heal".equals(field) && n > 100)))
                throw new IllegalArgumentException("Object 数值属性无效");
            if (properties.containsKey("trace_for") && !objects.containsKey(properties.get("trace_for"))) throw new IllegalArgumentException("痕迹引用无效");
            int positions = 0;
            for (String field : List.of("location", "holder", "container")) if (item.get(field) != null) positions++;
            if ("consumed".equals(item.get("state"))) {
                if (positions != 0 || !Boolean.FALSE.equals(item.get("visible"))) throw new IllegalArgumentException("已使用对象不能仍在 inventory");
            } else if (positions != 1) throw new IllegalArgumentException("Object 必须只有一个物理位置");
            if (item.get("location") != null && !((List<?>) world.get("locations")).contains(item.get("location"))) throw new IllegalArgumentException("Object 地点无效");
            if (item.get("owner") != null && !characters.containsKey(item.get("owner"))) throw new IllegalArgumentException("Object owner 无效");
            if (item.get("holder") != null && (!characters.containsKey(item.get("holder")) || !Boolean.TRUE.equals(item.get("portable")))) throw new IllegalArgumentException("Object holder 无效");
            if (Boolean.TRUE.equals(properties.get("container")) && Boolean.TRUE.equals(item.get("portable")))
                throw new IllegalArgumentException("本阶段容器必须固定且不可携带");
            if (item.get("container") != null) {
                var parent = map(objects.get(item.get("container")));
                if (parent == null || parent == item || parent.get("location") == null || parent.get("holder") != null
                        || !Boolean.TRUE.equals(map(parent.get("properties")).get("container")) || Boolean.TRUE.equals(map(item.get("properties")).get("container")))
                    throw new IllegalArgumentException("仅支持一层固定容器");
            }
        }
    }
    static String location(Map<String, Object> world, Map<String, Object> item) {
        if (item.get("holder") != null) return (String) map(map(world.get("characters")).get(item.get("holder"))).get("location");
        if (item.get("container") != null) return (String) map(map(world.get("objects")).get(item.get("container"))).get("location");
        return (String) item.get("location");
    }
    static boolean visible(Map<String, Object> world, Map<String, Object> item, String actor) {
        if (!Boolean.TRUE.equals(item.get("visible")) || !Objects.equals(location(world, item), map(map(world.get("characters")).get(actor)).get("location"))) return false;
        if (item.get("holder") != null && !actor.equals(item.get("holder"))) return false;
        if (item.get("container") != null) {
            var parent = map(map(world.get("objects")).get(item.get("container")));
            return Boolean.TRUE.equals(parent.get("visible")) && "open".equals(parent.get("state"));
        }
        return true;
    }
    static Map<String, Object> resolve(Map<String, Object> world, Map<String, Object> args, String actor) {
        var objects = map(world.get("objects"));
        if (args.containsKey("object_id")) {
            var item = map(objects.get(text(args.get("object_id"))));
            if (item == null) throw new IllegalArgumentException("Object 不存在");
            return item;
        }
        String label = text(args.containsKey("object_name") ? args.get("object_name") : args.get("item"));
        var found = objects.values().stream().map(WorldObjects::map).filter(item -> label.equals(item.get("name"))
                && Objects.equals(location(world, item), map(map(world.get("characters")).get(actor)).get("location"))).toList();
        if (found.size() != 1) throw new IllegalArgumentException("对象不存在或名称不唯一，请使用 object_id");
        return found.get(0);
    }
    static void project(Map<String, Object> world) {
        var objects = map(world.get("objects"));
        map(world.get("characters")).forEach((actor, raw) -> {
            var names = objects.values().stream().map(WorldObjects::map).filter(item -> actor.equals(item.get("holder"))).map(item -> item.get("name")).toList();
            if (map(raw).containsKey("items")) map(raw).put("items", new ArrayList<>(names));
        });
        var visible = new LinkedHashMap<String, Object>(); var allowed = new LinkedHashMap<String, Object>(); var hidden = new LinkedHashMap<String, Object>();
        for (Object raw : objects.values()) {
            var item = map(raw); String place = location(world, item); if (place == null || item.get("holder") != null) continue;
            var properties = map(item.get("properties"));
            boolean accessible = Boolean.TRUE.equals(item.get("visible")) && (item.get("container") == null ||
                    ("open".equals(map(objects.get(item.get("container"))).get("state")) && Boolean.TRUE.equals(map(objects.get(item.get("container"))).get("visible"))));
            if (accessible) map(visible.computeIfAbsent(place, ignored -> new LinkedHashMap<>())).put((String) item.get("name"), item.get("description"));
            if (Boolean.TRUE.equals(properties.get("legacy_concealable"))) {
                list(allowed.computeIfAbsent(place, ignored -> new ArrayList<>())).add(item.get("name"));
                if (!Boolean.TRUE.equals(item.get("visible"))) map(hidden.computeIfAbsent(place, ignored -> new LinkedHashMap<>())).put((String) item.get("name"),
                        Map.of("observation", item.get("description"), "trace_name", item.get("name") + "被移动的痕迹", "concealed_at_event_count", properties.getOrDefault("hidden_at_index", 0)));
            }
        }
        // 旧查询视图单向重建，旧字典不能反向覆盖 objects。
        world.put("inspectable_objects", visible); world.put("concealable_objects", allowed); world.put("concealed_objects", hidden);
    }
    static String apply(Map<String, Object> world, String tool, Map<String, Object> args) {
        ensure(world);
        String actor = text(args.get("give_item".equals(tool) ? "giver" : "character"));
        var person = map(map(world.get("characters")).get(actor));
        if (person == null) throw new IllegalArgumentException("角色不存在：" + actor);
        int cost = "inspect".equals(tool) || Set.of("conceal_clue", "recover_clue").contains(tool) ? 3 : 2;
        if ("unconscious".equals(person.get("status")) || ((Number) person.get("energy")).intValue() < cost) throw new IllegalArgumentException("角色失去行动能力或体力不足");
        String place = (String) person.get("location"), type = tool, target = null, result;
        var payload = new LinkedHashMap<String, Object>();
        Map<String, Object> item = null;
        if (!"inspect".equals(tool) || args.containsKey("object_id") || args.containsKey("object_name")) {
            item = resolve(world, args, actor); payload.put("object_id", item.get("id")); payload.put("object_name", item.get("name"));
        }
        switch (tool) {
            case "inspect": {
                if (item != null && !visible(world, item, actor)) throw new IllegalArgumentException("对象不可见或不可接近");
                String observation = item == null ? text(map(world.get("inspectables")).get(place)) : item.get("description") + " 状态：" + item.get("state");
                int since = item == null ? -1 : ((Number) map(item.get("properties")).getOrDefault("hidden_at_index", -1)).intValue();
                var history = list(world.get("events"));
                for (int index = since + 1; index < history.size(); index++) {
                    var event = map(history.get(index)); var old = map(event.get("payload"));
                    boolean same = item == null ? old.get("object_id") == null && old.get("object_name") == null :
                            item.get("id").equals(old.get("object_id")) || (old.get("object_id") == null && item.get("name").equals(old.get("object_name")));
                    if ("inspect".equals(event.get("type")) && actor.equals(event.get("actor")) && place.equals(event.get("location")) && same && observation.equals(old.get("observation")))
                        throw new IllegalArgumentException("已调查过，目前没有新发现");
                }
                payload.put("observation", observation); result = actor + "调查了" + (item == null ? place : item.get("name")) + "：" + observation;
                break;
            }
            case "take": {
                if (!visible(world, item, actor) || !Boolean.TRUE.equals(item.get("portable")) || item.get("holder") != null) throw new IllegalArgumentException("不能拿取：不可接近、不可携带或已有持有者");
                item.put("location", null); item.put("container", null); item.put("holder", actor);
                result = actor + "拿起了" + item.get("name") + "。"; break;
            }
            case "put": {
                if (!actor.equals(item.get("holder"))) throw new IllegalArgumentException("角色没有持有该对象");
                boolean toContainer = args.containsKey("container_id");
                if (toContainer == args.containsKey("location")) throw new IllegalArgumentException("put 必须选择一个地点或容器");
                if (toContainer) {
                    var container = map(map(world.get("objects")).get(text(args.get("container_id"))));
                    if (container == null || container == item || !visible(world, container, actor) || container.get("holder") != null || container.get("location") == null
                            || !Boolean.TRUE.equals(map(container.get("properties")).get("container")) || !"open".equals(container.get("state"))) throw new IllegalArgumentException("容器不存在、不可接近或没有打开");
                    item.put("container", container.get("id")); item.put("location", null);
                } else {
                    if (!place.equals(args.get("location"))) throw new IllegalArgumentException("只能放在当前合法地点");
                    item.put("location", place); item.put("container", null);
                }
                item.put("holder", null); result = actor + "放下了" + item.get("name") + "。"; payload.put("container_id", item.get("container")); break;
            }
            case "give", "give_item": {
                target = text(args.get("receiver")); var receiver = map(map(world.get("characters")).get(target));
                if (actor.equals(target) || receiver == null || !place.equals(receiver.get("location")) || "unconscious".equals(receiver.get("status")) || !actor.equals(item.get("holder")))
                    throw new IllegalArgumentException("交付要求本人持有且双方可行动、同地点");
                item.put("holder", target); // 保留 owner，支持借用；give 不自动转移法律归属。
                payload.put("item", item.get("name")); result = actor + "把" + item.get("name") + "交给了" + target + "。"; break;
            }
            case "use", "interact": {
                String action = text(args.get("action"));
                if (!visible(world, item, actor) || !((List<?>) item.get("affordances")).contains(action)) throw new IllegalArgumentException("对象不支持该 affordance 或不可接近");
                String before = (String) item.get("state"), after;
                switch (action) {
                    case "open": if (!"interact".equals(tool) || !"closed".equals(before)) throw new IllegalArgumentException("当前状态不能 open"); after = "open"; break;
                    case "close": if (!"interact".equals(tool) || !"open".equals(before)) throw new IllegalArgumentException("当前状态不能 close"); after = "closed"; break;
                    case "light": if (!"use".equals(tool) || !"extinguished".equals(before)) throw new IllegalArgumentException("当前状态不能 light"); after = "lit"; break;
                    case "extinguish": if (!"use".equals(tool) || !"lit".equals(before)) throw new IllegalArgumentException("当前状态不能 extinguish"); after = "extinguished"; break;
                    case "consume": {
                        Object healing = map(item.get("properties")).get("heal");
                        int hp = ((Number) person.getOrDefault("hp", 100)).intValue();
                        if (!"use".equals(tool) || !actor.equals(item.get("holder")) || !(healing instanceof Integer heal) || heal < 1 || hp >= 100) throw new IllegalArgumentException("consume 要求持有已定义药物且生命未满");
                        int afterHp = Math.min(100, hp + (Integer) healing); person.put("hp", afterHp); if (afterHp == 100) person.put("status", "normal");
                        item.put("holder", null); item.put("visible", false); payload.put("hp_after", afterHp); after = "consumed"; break;
                    }
                    default: throw new IllegalArgumentException("未知 interact/use action");
                }
                item.put("state", after); payload.put("action", action); payload.put("state_before", before); payload.put("state_after", after);
                result = actor + "对" + item.get("name") + "执行了" + action + "。"; break;
            }
            case "conceal_clue": {
                if (!visible(world, item, actor) || item.get("holder") != null || !Boolean.TRUE.equals(map(item.get("properties")).get("legacy_concealable"))) throw new IllegalArgumentException("该对象不能通过旧藏匿工具处理");
                String traceName = item.get("name") + "被移动的痕迹"; String id = stableId("scene\0" + place + "\0" + traceName);
                if (map(world.get("objects")).containsKey(id)) throw new IllegalArgumentException("现场已有痕迹");
                var trace = sceneObject(place, traceName, "此处有物件被移走的痕迹，无法直接查看原内容。");
                trace.put("portable", false); map(trace.get("properties")).put("trace_for", item.get("id"));
                int index = list(world.get("events")).size(); map(trace.get("properties")).put("hidden_at_index", index);
                map(item.get("properties")).put("hidden_at_index", index); item.put("visible", false); map(world.get("objects")).put(id, trace);
                type = "conceal"; payload.put("trace_name", traceName); result = actor + "藏起了" + item.get("name") + "，留下可调查痕迹。"; break;
            }
            case "recover_clue": {
                String traceId = stableId("scene\0" + place + "\0" + item.get("name") + "被移动的痕迹");
                var trace = map(map(world.get("objects")).get(traceId)); int since = ((Number) map(item.get("properties")).getOrDefault("hidden_at_index", 0)).intValue();
                boolean examined = false; var history = list(world.get("events"));
                for (int index = since + 1; index < history.size(); index++) {
                    var event = map(history.get(index)); var old = map(event.get("payload"));
                    if ("inspect".equals(event.get("type")) && actor.equals(event.get("actor")) && (traceId.equals(old.get("object_id")) || (trace != null && trace.get("name").equals(old.get("object_name"))))) examined = true;
                }
                if (!place.equals(location(world, item)) || Boolean.TRUE.equals(item.get("visible")) || trace == null || !examined) throw new IllegalArgumentException("需先亲自调查当前异常痕迹");
                item.put("visible", true); map(world.get("objects")).remove(traceId); type = "recover";
                result = actor + "找回了" + item.get("name") + "；尚未调查原件。"; break;
            }
            default: throw new IllegalArgumentException("未知对象动作");
        }
        person.put("energy", ((Number) person.get("energy")).intValue() - cost); project(world);
        var event = new LinkedHashMap<String, Object>(); event.put("id", UUID.randomUUID().toString().replace("-", ""));
        event.put("timestamp", world.get("time")); event.put("type", type); event.put("actor", actor); event.put("target", target);
        event.put("location", place); event.put("payload", payload); event.put("description", result);
        event.put("perceived_by", WorldRules.perceivedBy(world, type, actor, target, place)); list(world.get("events")).add(event);
        return result;
    }
}
