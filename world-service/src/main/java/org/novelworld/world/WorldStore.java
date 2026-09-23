package org.novelworld.world;

import tools.jackson.core.JacksonException;
import tools.jackson.databind.ObjectMapper;
import java.util.Map;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;
import org.springframework.data.redis.core.StringRedisTemplate;

@Repository
public class WorldStore {
    private final JdbcTemplate jdbc;
    private final StringRedisTemplate redis;
    private final ObjectMapper mapper;

    public WorldStore(JdbcTemplate jdbc, StringRedisTemplate redis, ObjectMapper mapper) {
        this.jdbc = jdbc;
        this.redis = redis;
        this.mapper = mapper;
    }

    @SuppressWarnings("unchecked")
    public Map<String, Object> load(String worldId) {
        String json = null;
        try { json = redis.opsForValue().get("world:" + worldId); }
        catch (RuntimeException ignored) { /* MySQL remains authoritative when Redis is unavailable. */ }
        if (json != null) {
            try {
                var cached = mapper.readValue(json, Map.class);
                var revisions = jdbc.queryForList("SELECT revision FROM world_saves WHERE world_id = ?", Long.class, worldId);
                if (!revisions.isEmpty() && revisions.get(0).longValue() == ((Number) cached.get("revision")).longValue())
                    return cached;
            } catch (RuntimeException ignored) { /* A stale or corrupt cache is ignored. */ }
            json = null;
        }
        if (json == null) {
            var rows = jdbc.queryForList("SELECT snapshot FROM world_saves WHERE world_id = ?", String.class, worldId);
            if (rows.isEmpty()) throw new IllegalArgumentException("世界不存在：" + worldId);
            json = rows.get(0);
        }
        try { return mapper.readValue(json, Map.class); }
        catch (JacksonException e) { throw new IllegalStateException("世界存档格式无效", e); }
    }

    public void insert(String worldId, Map<String, Object> snapshot) {
        jdbc.update("INSERT INTO world_saves(world_id, snapshot, revision) VALUES (?, ?, 0)", worldId, json(snapshot));
        cache(worldId, snapshot);
    }

    public void update(String worldId, Map<String, Object> snapshot) {
        long revision = ((Number) snapshot.get("revision")).longValue();
        snapshot.put("revision", revision + 1);
        int changed;
        try {
            changed = jdbc.update("UPDATE world_saves SET snapshot = ?, revision = ? WHERE world_id = ? AND revision = ?",
                    json(snapshot), revision + 1, worldId, revision);
        } catch (RuntimeException e) {
            snapshot.put("revision", revision);
            throw e;
        }
        if (changed != 1) {
            snapshot.put("revision", revision);
            throw new IllegalStateException("世界状态已由其他请求更新，请重新读取");
        }
        cache(worldId, snapshot);
    }

    public void queueEvent(String worldId, Map<String, Object> event) {
        try { redis.opsForList().rightPush("world:" + worldId + ":events", json(event)); }
        catch (RuntimeException ignored) { /* Event is durably stored in MySQL snapshot. */ }
    }

    private void cache(String worldId, Map<String, Object> snapshot) {
        try { redis.opsForValue().set("world:" + worldId, json(snapshot)); }
        catch (RuntimeException ignored) { /* Cache is rebuilt from MySQL. */ }
    }

    private String json(Object value) {
        try { return mapper.writeValueAsString(value); }
        catch (JacksonException e) { throw new IllegalArgumentException("状态无法序列化", e); }
    }
}
