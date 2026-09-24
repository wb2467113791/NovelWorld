package org.novelworld.world;

import java.util.Map;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** 作者偶尔影响环境；由 Java 校验并提交事件，NPC 后续自行决定反应。 */
@RestController
@RequestMapping("/api")
public class WorldInterventionController {
    private final AgentRuntimeClient runtime;
    private final WorldMcpTools world;

    public WorldInterventionController(AgentRuntimeClient runtime, WorldMcpTools world) {
        this.runtime = runtime;
        this.world = world;
    }

    @PostMapping("/world-events")
    public Map<String, Object> inject(@RequestBody Map<String, Object> request) {
        String worldId = (String) runtime.status().get("world_id");
        return world.injectWorldEvent(worldId, text(request, "location"),
                text(request, "object_name"), text(request, "observation"));
    }

    private static String text(Map<String, Object> request, String key) {
        Object value = request.get(key);
        if (!(value instanceof String result) || result.isBlank())
            throw new IllegalArgumentException(key + " 不能为空");
        return result;
    }

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<Map<String, String>> invalid(IllegalArgumentException error) {
        return ResponseEntity.badRequest().body(Map.of("detail", error.getMessage()));
    }
}
