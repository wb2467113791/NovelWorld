package org.novelworld.world;

import java.util.LinkedHashMap;
import java.util.Map;

/** Deprecated 外部调用参数兼容；不结算行为、不参与 Agent 正式工具声明。 */
final class LegacyWorldTools {
    private LegacyWorldTools() {}
    record Request(String name, Map<String, Object> arguments) {}

    static Request normalize(String name, Map<String, Object> args) {
        if ("give_item".equals(name)) {
            var mapped = new LinkedHashMap<>(args);
            mapped.put("character", args.get("giver"));
            return new Request("give", mapped);
        }
        if ("world_action".equals(name) && ("use_item".equals(args.get("action")) || "interact".equals(args.get("action")))) {
            var mapped = new LinkedHashMap<>(args);
            mapped.put("character", args.get("actor"));
            boolean consume = "use_item".equals(args.get("action"));
            mapped.put("action", consume ? "consume" : args.get("interaction"));
            return new Request(consume ? "use" : "interact", mapped);
        }
        return new Request(name, args);
    }
}
