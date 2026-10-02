package org.novelworld.world;

import java.util.List;
import java.util.Map;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;
import tools.jackson.databind.ObjectMapper;

/** MySQL 持久化与 revision 乐观锁。旧存档原样保存，不在读时自动改写。 */
@Repository
public class WorldStore {
    private final JdbcTemplate jdbc;
    private final ObjectMapper mapper;
    public WorldStore(JdbcTemplate jdbc, ObjectMapper mapper) { this.jdbc = jdbc; this.mapper = mapper; }
    @SuppressWarnings("unchecked")
    public Map<String, Object> load(String worldId) {
        var rows = jdbc.queryForList("SELECT snapshot FROM world_saves WHERE world_id = ?", String.class, worldId);
        if (rows.isEmpty()) throw new IllegalArgumentException("世界不存在：" + worldId);
        return mapper.readValue(rows.get(0), Map.class);
    }
    public void insert(String worldId, Map<String, Object> snapshot) {
        jdbc.update("INSERT INTO world_saves(world_id, snapshot, revision) VALUES (?, ?, 0)", worldId, mapper.writeValueAsString(snapshot));
    }
    public List<String> listWorldIds() { return jdbc.queryForList("SELECT world_id FROM world_saves ORDER BY world_id", String.class); }
    public void update(String worldId, Map<String, Object> snapshot) {
        long revision = ((Number) snapshot.get("revision")).longValue(); snapshot.put("revision", revision + 1);
        try {
            if (jdbc.update("UPDATE world_saves SET snapshot = ?, revision = ? WHERE world_id = ? AND revision = ?",
                    mapper.writeValueAsString(snapshot), revision + 1, worldId, revision) != 1)
                throw new IllegalStateException("世界已更新，请重新读取");
        } catch (RuntimeException error) { snapshot.put("revision", revision); throw error; }
    }
}
