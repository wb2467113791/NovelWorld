package org.novelworld.world;

import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

/** 作者配置开局；创建新世界不会切换或覆盖当前运行的世界。 */
@RestController
@RequestMapping("/api")
public class WorldSetupController {
    private final WorldTemplateService templates;
    private final WorldStore store;
    private final AgentRuntimeClient runtime;

    public WorldSetupController(WorldTemplateService templates, WorldStore store, AgentRuntimeClient runtime) {
        this.templates = templates;
        this.store = store;
        this.runtime = runtime;
    }

    @GetMapping("/world-template/default")
    public Map<String, Object> defaultTemplate() {
        return templates.defaultTemplate();
    }

    @PostMapping("/worlds")
    public ResponseEntity<Map<String, String>> createWorld(@RequestBody Map<String, Object> template) {
        requirePaused();
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(Map.of("world_id", templates.createWorld(template)));
    }

    @GetMapping("/worlds")
    public Map<String, Object> worlds() {
        return Map.of("world_ids", store.listWorldIds(),
                "active_world_id", runtime.status().get("world_id"));
    }

    @PostMapping("/worlds/{worldId}/activate")
    public Map<String, Object> activateWorld(@PathVariable String worldId) {
        requirePaused();
        try {
            store.load(worldId);
        } catch (IllegalArgumentException error) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, error.getMessage(), error);
        }
        return runtime.control("activate", Map.of("world_id", worldId));
    }

    private void requirePaused() {
        if (Boolean.TRUE.equals(runtime.status().get("running")))
            throw new ResponseStatusException(HttpStatus.CONFLICT, "请先暂停当前世界");
    }

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<Map<String, String>> invalidTemplate(IllegalArgumentException error) {
        return ResponseEntity.badRequest().body(Map.of("detail", error.getMessage()));
    }
}
