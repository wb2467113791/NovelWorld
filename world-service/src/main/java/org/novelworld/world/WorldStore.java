package org.novelworld.world;

import tools.jackson.core.JacksonException;
import tools.jackson.databind.ObjectMapper;
import java.util.List;
import java.util.Map;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class WorldStore {
    private final JdbcTemplate jdbc;
    private final ObjectMapper mapper;

    public WorldStore(JdbcTemplate jdbc, ObjectMapper mapper) {
        this.jdbc = jdbc;
        this.mapper = mapper;
    }

    @SuppressWarnings("unchecked")
    public Map<String, Object> load(String worldId) {
        var rows = jdbc.queryForList("SELECT snapshot FROM world_saves WHERE world_id = ?", String.class, worldId);
        if (rows.isEmpty()) throw new IllegalArgumentException("世界不存在：" + worldId);
        String json = rows.get(0);
        try { Map<String, Object> world = mapper.readValue(json, Map.class); WorldActors.ensure(world); WorldObjects.ensure(world); return world; }
        catch (JacksonException e) { throw new IllegalStateException("世界存档格式无效", e); }
    }

    public void insert(String worldId, Map<String, Object> snapshot) {
        WorldActors.ensure(snapshot);
        WorldObjects.ensure(snapshot);
        jdbc.update("INSERT INTO world_saves(world_id, snapshot, revision) VALUES (?, ?, 0)", worldId, json(snapshot));
    }

    public List<String> listWorldIds() {
        return jdbc.queryForList("SELECT world_id FROM world_saves ORDER BY world_id", String.class);
    }

    public boolean delete(String worldId) {
        return jdbc.update("DELETE FROM world_saves WHERE world_id = ?", worldId) == 1;
    }

    public void update(String worldId, Map<String, Object> snapshot) {
        WorldActors.ensure(snapshot);
        WorldObjects.ensure(snapshot);
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
    }

    private String json(Object value) {
        try { return mapper.writeValueAsString(value); }
        catch (JacksonException e) { throw new IllegalArgumentException("状态无法序列化", e); }
    }
}
