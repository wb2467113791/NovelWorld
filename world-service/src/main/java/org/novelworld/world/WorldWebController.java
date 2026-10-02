package org.novelworld.world;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;
import tools.jackson.databind.ObjectMapper;

/** 浏览器唯一入口。Observe 展示群像，Play 仅提供玩家可见资料。 */
@RestController
@RequestMapping("/api")
public class WorldWebController {
    private final WorldStore store;
    private final AgentRuntimeClient runtime;
    private final ObjectMapper mapper;
    public WorldWebController(WorldStore store, AgentRuntimeClient runtime, ObjectMapper mapper) {
        this.store = store; this.runtime = runtime; this.mapper = mapper;
    }
    static Map<String, Object> view(Map<String, Object> w, Map<String, Object> status, boolean play) {
        var v = new LinkedHashMap<String, Object>();
        for (String key : List.of("world_id", "revision", "title", "premise", "minute", "time", "tick_count", "locations", "activities")) v.put(key, w.get(key));
        for (String key : List.of("running", "pausing", "error", "acting", "phase")) v.put(key, status.get(key));
        v.put("event_count", WorldRules.list(w.get("events")).size());
        var people = WorldRules.map(w.get("characters"));
        String player = people.entrySet().stream().filter(e -> "player".equals(WorldRules.map(e.getValue()).get("actor_type")))
                .map(Map.Entry::getKey).findFirst().orElse(null);
        v.put("player_name", player);
        String location = player == null ? null : (String) WorldRules.actor(w, player).get("location");
        var visiblePeople = new LinkedHashMap<String, Object>();
        people.forEach((name, raw) -> {
            var p = WorldRules.map(raw);
            if (play) {
                if (!name.equals(player) && !p.get("location").equals(location)) return;
                var summary = new LinkedHashMap<String, Object>();
                for (String key : List.of("name", "role", "actor_type", "location", "activity")) summary.put(key, p.get(key));
                visiblePeople.put(name, summary);
            } else {
                var summary = new LinkedHashMap<>(p);
                var memories = WorldRules.list(p.getOrDefault("memories", List.of()));
                summary.put("memories", new ArrayList<>(memories.subList(Math.max(0, memories.size() - 18), memories.size())));
                visiblePeople.put(name, summary);
            }
        });
        v.put("characters", visiblePeople);
        var events = WorldRules.list(w.get("events")).stream().map(WorldRules::map)
                .filter(e -> !play || (player != null && WorldRules.list(e.get("perceived_by")).contains(player))).toList();
        v.put("events", events.subList(Math.max(0, events.size() - 120), events.size()));
        v.put("decisions", play ? List.of() : w.get("decisions"));
        v.put("invitations", WorldRules.list(w.get("invitations")).stream().map(WorldRules::map)
                .filter(i -> !play || i.get("from").equals(player) || i.get("to").equals(player)).toList());
        v.put("conversations", WorldRules.list(w.get("conversations")).stream().map(WorldRules::map)
                .filter(s -> !play || WorldRules.list(s.get("participants")).contains(player)).toList());
        var objects = new LinkedHashMap<String, Object>();
        WorldRules.map(w.get("objects")).forEach((id, raw) -> {
            var o = WorldRules.map(raw);
            if (!play || o.get("location").equals(location)) objects.put(id, Map.of("name", o.get("name"), "location", o.get("location")));
        });
        v.put("objects", objects); return v;
    }
    @GetMapping("/world")
    public Map<String, Object> world(@RequestParam(defaultValue = "observe") String mode) {
        if (!List.of("observe", "play").contains(mode)) throw new IllegalArgumentException("视角无效");
        var status = runtime.status();
        return view(store.load((String) status.get("world_id")), status, "play".equals(mode));
    }
    @PostMapping("/control/next") public Map<String, Object> next() { return runtime.control("next", Map.of()); }
    @PostMapping("/control/run") public Map<String, Object> run(@RequestBody Map<String, Object> body) { return runtime.control("run", body); }
    @PostMapping("/control/pause") public Map<String, Object> pause() { return runtime.control("pause", Map.of()); }
    @PostMapping("/play/join") public Map<String, Object> join(@RequestBody Map<String, Object> body) { return runtime.play("join", body); }
    @PostMapping("/play/action") public Map<String, Object> action(@RequestBody Map<String, Object> body) { return runtime.play("action", body); }

    @GetMapping(value = "/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter events(@RequestParam(defaultValue = "observe") String mode) {
        if (!List.of("observe", "play").contains(mode)) throw new IllegalArgumentException("视角无效");
        var emitter = new SseEmitter(30 * 60_000L); var closed = new AtomicBoolean(false);
        emitter.onCompletion(() -> closed.set(true)); emitter.onTimeout(() -> closed.set(true)); emitter.onError(e -> closed.set(true));
        var worker = new Thread(() -> {
            String previous = null; int idle = 0;
            try {
                while (!closed.get()) {
                    String value = mapper.writeValueAsString(world(mode));
                    if (!value.equals(previous)) { emitter.send(SseEmitter.event().name("state").data(value)); previous = value; idle = 0; }
                    else if (++idle >= 15) { emitter.send(SseEmitter.event().comment("keepalive")); idle = 0; }
                    Thread.sleep(1000);
                }
            } catch (InterruptedException e) { Thread.currentThread().interrupt(); emitter.complete(); }
            catch (Exception e) { emitter.completeWithError(e); }
        }, "world-sse");
        worker.setDaemon(true); worker.start(); return emitter;
    }
}
