package org.novelworld.world;

import tools.jackson.databind.ObjectMapper;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.regex.Pattern;
import org.springframework.stereotype.Component;

@Component
public class WorldRules {
    private static final Pattern REVIEW_CLAIM = Pattern.compile("(?:我|本人)(?:已|已经)?(?:看过|查过|翻过|过目|调查过|核对过|看了|查了|调查了)");
    private static final Map<String, String> OBJECT_ALIASES = Map.of("住客登记簿", "登记簿", "柴房门锁", "柴房");
    private static final Map<String, Integer> ENERGY_COSTS = Map.of(
            "move_character", 5, "inspect", 3, "talk", 2,
            "give_item", 2, "update_relationship", 1);
    private final ObjectMapper mapper;

    public WorldRules(ObjectMapper mapper) { this.mapper = mapper; }
    @SuppressWarnings("unchecked")
    private static Map<String, Object> map(Object value) { return (Map<String, Object>) value; }
    @SuppressWarnings("unchecked")
    private static List<Object> list(Object value) { return (List<Object>) value; }
    private static String str(Map<String, Object> map, String key) {
        Object value = map.get(key);
        if (!(value instanceof String text) || text.isBlank()) throw new IllegalArgumentException("参数不能为空：" + key);
        return text;
    }
    private static Map<String, Object> character(Map<String, Object> world, String name) {
        Object result = map(world.get("characters")).get(name);
        if (result == null) throw new IllegalArgumentException("角色不存在：" + name);
        return map(result);
    }
    private static void requireEnergy(Map<String, Object> person, String actor, String action) {
        if ("unconscious".equals(person.get("status"))) throw new IllegalArgumentException(actor + "失去行动能力");
        int cost = ENERGY_COSTS.get(action);
        if (((Number) person.get("energy")).intValue() < cost)
            throw new IllegalArgumentException(actor + "体力不足，执行" + action + "需要" + cost + "点体力");
    }
    static List<String> perceivedBy(Map<String, Object> world, String type, String actor,
                                    String target, String location) {
        var recipients = new java.util.ArrayList<String>();
        var characters = map(world.get("characters"));
        if (characters.containsKey(actor)) recipients.add(actor);
        if (("talk".equals(type) || "give_item".equals(type)) && target != null && characters.containsKey(target))
            recipients.add(target);
        if (List.of("move", "flee", "follow", "attack", "interact", "director").contains(type)) {
            for (var entry : characters.entrySet()) {
                if (!recipients.contains(entry.getKey()) && location.equals(map(entry.getValue()).get("location")))
                    recipients.add(entry.getKey());
            }
        }
        return recipients;
    }

    public String apply(Map<String, Object> world, String name, Map<String, Object> args) {
        if ("world_action".equals(name)) return applyWorldAction(world, args);
        String actor, target, location, result;
        Map<String, Object> payload;
        String type;
        switch (name) {
            case "get_world_time": return (String) world.get("time");
            case "get_character": {
                var person = character(world, str(args, "character"));
                return mapper.writeValueAsString(Map.of("name", person.get("name"), "role", person.get("role"),
                        "location", person.get("location"), "energy", person.get("energy"),
                        "relationships", person.get("relationships")));
            }
            case "move_character": {
                actor = str(args, "character"); location = str(args, "location");
                if (!list(world.get("locations")).contains(location)) throw new IllegalArgumentException("地点不存在：" + location);
                var person = character(world, actor);
                requireEnergy(person, actor, name);
                String old = (String) person.put("location", location);
                result = old.equals(location) ? actor + "已经在" + location + "。" : actor + "从" + old + "移动到" + location + "。";
                type = "move"; target = null; payload = Map.of("from", old, "to", location);
                break;
            }
            case "talk": {
                actor = str(args, "speaker"); target = str(args, "listener");
                if (actor.equals(target)) throw new IllegalArgumentException("角色不能和自己交谈");
                var speaker = character(world, actor); var listener = character(world, target);
                location = (String) speaker.get("location");
                if (!location.equals(listener.get("location"))) throw new IllegalArgumentException("双方不在同一地点");
                String message = str(args, "message").trim();
                var objectsByPlace = map(world.get("inspectable_objects"));
                for (Object placeObjects : objectsByPlace.values()) {
                    for (String objectName : map(placeObjects).keySet()) {
                        boolean claimed = false;
                        for (String sentence : message.split("[。！？\\n]")) {
                            if (REVIEW_CLAIM.matcher(sentence).find() && (sentence.contains(objectName)
                                    || sentence.contains(OBJECT_ALIASES.getOrDefault(objectName, objectName)))) claimed = true;
                        }
                        if (claimed && list(world.get("events")).stream().map(WorldRules::map).noneMatch(event ->
                                "inspect".equals(event.get("type")) && actor.equals(event.get("actor"))
                                        && objectName.equals(map(event.get("payload")).get("object_name"))))
                            throw new IllegalArgumentException(actor + "尚未调查" + objectName + "，不能声称已经查看");
                    }
                }
                requireEnergy(speaker, actor, name);
                result = actor + "对" + target + "说：“" + message + "”";
                type = "talk"; payload = Map.of("message", message);
                break;
            }
            case "give_item": {
                actor = str(args, "giver"); target = str(args, "receiver");
                String item = str(args, "item");
                if (actor.equals(target)) throw new IllegalArgumentException("角色不能把物品交给自己");
                var giver = character(world, actor); var receiver = character(world, target);
                location = (String) giver.get("location");
                if (!location.equals(receiver.get("location"))) throw new IllegalArgumentException("双方不在同一地点");
                if (!list(giver.get("items")).contains(item)) throw new IllegalArgumentException(actor + "不拥有物品：" + item);
                requireEnergy(giver, actor, name);
                list(giver.get("items")).remove(item); list(receiver.get("items")).add(item);
                result = actor + "在" + location + "把" + item + "交给了" + target + "。";
                type = "give_item"; payload = Map.of("item", item);
                break;
            }
            case "update_relationship": {
                actor = str(args, "character"); target = str(args, "target");
                if (actor.equals(target)) throw new IllegalArgumentException("角色不能修改与自己的关系");
                var person = character(world, actor); character(world, target);
                Object raw = args.get("change");
                if (!(raw instanceof Number number) || number.doubleValue() != number.intValue()) throw new IllegalArgumentException("关系变化值必须是整数");
                var relationships = map(person.get("relationships"));
                int old = ((Number) relationships.getOrDefault(target, 0)).intValue();
                int next = Math.max(-100, Math.min(100, old + number.intValue()));
                requireEnergy(person, actor, name);
                relationships.put(target, next);
                location = (String) person.get("location");
                result = actor + "对" + target + "的关系值从" + old + "变为" + next + "。";
                type = "relationship"; payload = Map.of("change", number.intValue(), "old_value", old, "new_value", next);
                break;
            }
            case "inspect": {
                actor = str(args, "character"); var person = character(world, actor);
                location = (String) person.get("location");
                Object object = args.get("object_name");
                Object observation = object == null ? map(world.get("inspectables")).get(location)
                        : map(map(world.get("inspectable_objects")).getOrDefault(location, Map.of())).get(object);
                if (observation == null) throw new IllegalArgumentException("地点或对象无法调查");
                for (Object raw : list(world.get("events"))) {
                    var event = map(raw); var previous = map(event.get("payload"));
                    if ("inspect".equals(event.get("type")) && actor.equals(event.get("actor"))
                            && location.equals(event.get("location")) && java.util.Objects.equals(object, previous.get("object_name"))
                            && observation.equals(previous.get("observation"))) throw new IllegalArgumentException("已调查过，目前没有新发现");
                }
                requireEnergy(person, actor, name);
                result = actor + "调查了" + location + (object == null ? "" : "的" + object) + "：" + observation;
                type = "inspect"; target = null;
                payload = new java.util.HashMap<>(); payload.put("observation", observation);
                if (object != null) payload.put("object_name", object);
                break;
            }
            case "rest_character": {
                actor = str(args, "character"); var person = character(world, actor);
                int before = ((Number) person.get("energy")).intValue();
                if (before >= 100) throw new IllegalArgumentException(actor + "体力已满，无需休息");
                int after = Math.min(100, before + 20);
                person.put("energy", after);
                location = (String) person.get("location"); target = null;
                result = actor + "休息后体力从" + before + "恢复到" + after + "。";
                type = "rest"; payload = Map.of("energy_before", before, "energy_after", after);
                break;
            }
            default: throw new IllegalArgumentException("未知工具：" + name);
        }
        if (ENERGY_COSTS.containsKey(name)) {
            var person = character(world, actor);
            person.put("energy", ((Number) person.get("energy")).intValue() - ENERGY_COSTS.get(name));
        }
        var event = new java.util.LinkedHashMap<String, Object>();
        event.put("id", UUID.randomUUID().toString().replace("-", ""));
        event.put("timestamp", world.get("time")); event.put("type", type);
        event.put("actor", actor); event.put("target", target); event.put("location", location);
        var witnesses = perceivedBy(world, type, actor, target, location);
        if ("move".equals(type)) {
            String departure = (String) payload.get("from");
            for (var entry : map(world.get("characters")).entrySet()) {
                if (departure.equals(map(entry.getValue()).get("location")) && !witnesses.contains(entry.getKey()))
                    witnesses.add(entry.getKey());
            }
        }
        event.put("perceived_by", witnesses);
        event.put("payload", payload); event.put("description", result);
        list(world.get("events")).add(event);
        return result;
    }

    /** 新动作首版均使用确定性规则；模型只能提出意图。 */
    private String applyWorldAction(Map<String, Object> world, Map<String, Object> args) {
        String action = str(args, "action");
        String actor = str(args, "actor");
        var person = character(world, actor);
        String location = (String) person.get("location");
        String target = null;
        String result;
        int cost;
        var payload = new java.util.LinkedHashMap<String, Object>();
        Map<String, Object> other = null;
        int hpAfter = 0;
        String oldLocation = location;
        switch (action) {
            case "attack": {
                target = str(args, "target");
                if (actor.equals(target)) throw new IllegalArgumentException("不能攻击自己");
                other = character(world, target);
                if (!location.equals(other.get("location"))) throw new IllegalArgumentException("攻击目标不在同一地点");
                if ("unconscious".equals(other.get("status"))) throw new IllegalArgumentException("目标已失去行动能力");
                cost = 10;
                hpAfter = Math.max(0, ((Number) other.getOrDefault("hp", 100)).intValue() - 20);
                payload.put("damage", 20); payload.put("hp_after", hpAfter);
                result = actor + "攻击了" + target + "，造成20点伤害。";
                break;
            }
            case "use_item": {
                String item = str(args, "item");
                if (!list(person.get("items")).contains(item)) throw new IllegalArgumentException(actor + "不拥有物品：" + item);
                if (!item.contains("药")) throw new IllegalArgumentException("该物品没有已定义的使用规则：" + item);
                if (((Number) person.getOrDefault("hp", 100)).intValue() >= 100)
                    throw new IllegalArgumentException("生命值已满，无需使用药物");
                cost = 2;
                hpAfter = Math.min(100, ((Number) person.getOrDefault("hp", 100)).intValue() + 20);
                payload.put("item", item); payload.put("hp_after", hpAfter);
                result = actor + "使用" + item + "，生命值恢复至" + hpAfter + "。";
                break;
            }
            case "flee": {
                String destination = str(args, "location");
                if (!list(world.get("locations")).contains(destination) || destination.equals(location))
                    throw new IllegalArgumentException("逃离地点无效");
                cost = 7;
                payload.put("from", location); payload.put("to", destination);
                result = actor + "从" + location + "逃到了" + destination + "。";
                location = destination;
                break;
            }
            case "follow": {
                target = str(args, "target");
                if (actor.equals(target)) throw new IllegalArgumentException("不能跟随自己");
                other = character(world, target);
                String destination = (String) other.get("location");
                if (destination.equals(location)) throw new IllegalArgumentException("目标尚未离开当前地点");
                boolean seenDeparture = false;
                var history = list(world.get("events"));
                for (int i = history.size() - 1; i >= 0; i--) {
                    var event = map(history.get(i));
                    if (!List.of("move", "flee", "follow").contains(event.get("type")) || !target.equals(event.get("actor")))
                        continue;
                    var movement = map(event.get("payload"));
                    seenDeparture = oldLocation.equals(movement.get("from"))
                            && destination.equals(movement.get("to"))
                            && list(event.getOrDefault("perceived_by", List.of())).contains(actor);
                    break;
                }
                if (!seenDeparture) throw new IllegalArgumentException("角色没有目击目标离开，无法跟随");
                cost = 5;
                payload.put("from", location); payload.put("to", destination);
                result = actor + "跟随" + target + "来到" + destination + "。";
                location = destination;
                break;
            }
            case "interact": {
                String objectName = str(args, "object_name");
                var objects = map(world.get("inspectable_objects"));
                if (!map(objects.getOrDefault(location, Map.of())).containsKey(objectName))
                    throw new IllegalArgumentException("当前位置没有这个互动对象：" + objectName);
                cost = 2;
                payload.put("object_name", objectName);
                result = actor + "与" + location + "的" + objectName + "互动。";
                break;
            }
            default: throw new IllegalArgumentException("未知行动：" + action);
        }
        int energy = ((Number) person.get("energy")).intValue();
        if ("unconscious".equals(person.get("status"))) throw new IllegalArgumentException(actor + "失去行动能力");
        if (energy < cost) throw new IllegalArgumentException(actor + "体力不足，执行" + action + "需要" + cost + "点体力");
        person.put("energy", energy - cost);
        if ("attack".equals(action)) {
            other.put("hp", hpAfter);
            other.put("status", hpAfter == 0 ? "unconscious" : "injured");
        } else if ("use_item".equals(action)) {
            person.put("hp", hpAfter);
            if (hpAfter == 100) person.put("status", "normal");
            list(person.get("items")).remove(payload.get("item"));
        } else if ("flee".equals(action) || "follow".equals(action)) {
            person.put("location", location);
        }
        var event = new java.util.LinkedHashMap<String, Object>();
        event.put("id", UUID.randomUUID().toString().replace("-", ""));
        event.put("timestamp", world.get("time")); event.put("type", action);
        event.put("actor", actor); event.put("target", target); event.put("location", location);
        var witnesses = perceivedBy(world, action, actor, target, location);
        if ("flee".equals(action) || "follow".equals(action)) {
            for (var entry : map(world.get("characters")).entrySet()) {
                if (oldLocation.equals(map(entry.getValue()).get("location")) && !witnesses.contains(entry.getKey()))
                    witnesses.add(entry.getKey());
            }
        }
        event.put("perceived_by", witnesses);
        event.put("payload", payload); event.put("description", result);
        list(world.get("events")).add(event);
        return result;
    }
}
