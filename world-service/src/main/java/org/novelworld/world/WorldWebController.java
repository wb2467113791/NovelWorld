package org.novelworld.world;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;
import tools.jackson.databind.ObjectMapper;

/** 浏览器的唯一 API 入口；世界资料直接从 Java 持久状态读取。 */
@RestController
@RequestMapping("/api")
public class WorldWebController {
    private final WorldStore store;
    private final AgentRuntimeClient runtime;
    private final ObjectMapper mapper;

    public WorldWebController(WorldStore store, AgentRuntimeClient runtime, ObjectMapper mapper) {
        this.store = store;
        this.runtime = runtime;
        this.mapper = mapper;
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> map(Object value) { return (Map<String, Object>) value; }
    @SuppressWarnings("unchecked")
    private static List<Object> list(Object value) { return (List<Object>) value; }

    private Map<String, Object> savedWorld(Map<String, Object> status) {
        return store.load((String) status.get("world_id"));
    }

    private Map<String, Object> publicWorld(Map<String, Object> world, Map<String, Object> status) {
        var view = new LinkedHashMap<String, Object>();
        view.put("world_id", world.get("world_id"));
        view.put("time", world.get("time"));
        view.put("tick_count", status.get("tick_count"));
        view.put("event_count", list(world.get("events")).size());
        view.put("locations", world.get("locations"));
        var characters = new LinkedHashMap<String, Object>();
        map(world.get("characters")).forEach((name, raw) -> {
            var person = map(raw);
            if (!WorldActors.isNpc(person)) return;
            var summary = new LinkedHashMap<String, Object>();
            for (String field : List.of("name", "role", "location", "energy", "hp", "status", "goals", "items", "relationships"))
                summary.put(field, person.get(field));
            characters.put(name, summary);
        });
        view.put("characters", characters);
        var events = list(world.get("events"));
        view.put("events", new ArrayList<>(events.subList(Math.max(0, events.size() - 80), events.size())));
        view.put("running", status.get("running"));
        view.put("error", status.get("error"));
        return view;
    }

    @GetMapping("/world")
    public Map<String, Object> world() {
        var status = runtime.status();
        return publicWorld(savedWorld(status), status);
    }

    private static List<String> contents(List<Object> entries) {
        return entries.stream().map(item -> (String) map(item).get("content")).toList();
    }

    @GetMapping("/characters/{name}/view")
    public Map<String, Object> characterView(@PathVariable String name) {
        var status = runtime.status();
        var personValue = map(savedWorld(status).get("characters")).get(name);
        if (personValue == null) throw new ResponseStatusException(HttpStatus.NOT_FOUND, "角色不存在");
        var person = map(personValue);
        if (!WorldActors.isNpc(person)) throw new ResponseStatusException(HttpStatus.NOT_FOUND, "Player 没有 NPC 记忆视角");
        var memory = map(person.get("memory"));
        var archive = list(memory.get("archive"));
        var semantic = map(person.get("semantic_memory"));
        var facts = list(semantic.get("facts"));
        var view = new LinkedHashMap<String, Object>();
        for (String field : List.of("name", "role", "personality", "goals", "known_facts"))
            view.put(field, person.get(field));
        view.put("recent_memories", contents(list(memory.get("entries"))));
        view.put("archived_memories", contents(archive.subList(Math.max(0, archive.size() - 20), archive.size())));
        view.put("semantic_facts", facts.stream().map(item -> map(item).get("observation")).toList());
        return view;
    }

    @PostMapping("/control/next")
    public ResponseEntity<Map<String, Object>> next() {
        return ResponseEntity.accepted().body(runtime.control("next", Map.of()));
    }

    @PostMapping("/control/run")
    public ResponseEntity<Map<String, Object>> run(@RequestBody Map<String, Object> request) {
        return ResponseEntity.accepted().body(runtime.control("run", request));
    }

    @PostMapping("/control/pause")
    public Map<String, Object> pause() { return runtime.control("pause", Map.of()); }

    @GetMapping("/play/state")
    public Map<String, Object> playState() { return runtime.play("state", Map.of()); }

    @PostMapping("/play/action")
    public Map<String, Object> playAction(@RequestBody Map<String, Object> request) {
        return runtime.play("action", request);
    }

    @PostMapping("/play/conversation/end")
    public Map<String, Object> endPlayerConversation(@RequestBody Map<String, Object> request) {
        return runtime.play("conversation/end", request);
    }

    @GetMapping("/world-events")
    public Map<String, Object> worldEvents(@RequestParam(defaultValue = "0") int after) {
        var status = runtime.status();
        var events = list(savedWorld(status).get("events"));
        if (after < 0 || after > events.size()) throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "事件游标无效");
        int end = Math.min(events.size(), after + 100);
        return Map.of("events", new ArrayList<>(events.subList(after, end)), "next_cursor", end);
    }

    @GetMapping(value = "/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter events(@RequestParam(defaultValue = "observe") String mode) {
        if (!List.of("observe", "play").contains(mode))
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "观察模式无效");
        var emitter = new SseEmitter(0L);
        CompletableFuture.runAsync(() -> {
            String previous = null;
            int idleSeconds = 0;
            try {
                while (true) {
                    var status = runtime.status();
                    var saved = savedWorld(status);
                    String json = mapper.writeValueAsString("play".equals(mode) ? playRefresh(saved, status) : publicWorld(saved, status));
                    if (!json.equals(previous)) {
                        emitter.send(SseEmitter.event().name("state").data(json));
                        previous = json;
                        idleSeconds = 0;
                    } else if (++idleSeconds >= 15) {
                        emitter.send(SseEmitter.event().comment("keepalive"));
                        idleSeconds = 0;
                    }
                    Thread.sleep(1000);
                }
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
                emitter.complete();
            } catch (Exception error) {
                emitter.completeWithError(error);
            }
        });
        return emitter;
    }

    static Map<String, Object> playRefresh(Map<String, Object> world, Map<String, Object> status) {
        var view = new LinkedHashMap<String, Object>();
        for (String field : List.of("world_id", "tick_count", "running")) view.put(field, status.get(field));
        view.put("time", world.get("time"));
        view.put("event_count", list(world.get("events")).size());
        view.put("revision", world.get("revision"));
        return view;
    }
}
