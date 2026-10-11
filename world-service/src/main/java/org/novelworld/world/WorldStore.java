package org.novelworld.world;

import java.util.List;
import java.util.Map;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;
import tools.jackson.databind.ObjectMapper;

/** MySQL 快照、持久行动回执与 revision 乐观锁。v3 的旧 Decision 在同一事务中迁移。 */
@Repository
public class WorldStore {
    private final JdbcTemplate jdbc;
    private final ObjectMapper mapper;
    public WorldStore(JdbcTemplate jdbc, ObjectMapper mapper) { this.jdbc = jdbc; this.mapper = mapper; }
    @SuppressWarnings("unchecked")
    @Transactional
    public Map<String, Object> load(String worldId) {
        var rows = jdbc.queryForList("SELECT snapshot FROM world_saves WHERE world_id = ?", String.class, worldId);
        if (rows.isEmpty()) throw new IllegalArgumentException("世界不存在：" + worldId);
        Map<String, Object> w = mapper.readValue(rows.get(0), Map.class);
        if (Integer.valueOf(3).equals(w.get("version")) && w.containsKey("decisions")) {
            for (Object raw : WorldRules.list(w.get("decisions"))) {
                var trace = new java.util.LinkedHashMap<>(WorldRules.map(raw));
                String requestId = (String) trace.get("id");
                trace.put("status", "committed");
                if (execution(worldId, requestId) == null) saveExecution(worldId, requestId, trace);
                var ids = WorldRules.list(trace.get("event_ids"));
                for (Object event : WorldRules.list(w.get("events"))) {
                    var e = WorldRules.map(event);
                    if (ids.contains(e.get("id"))) e.put("request_id", requestId);
                    if (!ids.isEmpty() && ids.get(ids.size() - 1).equals(e.get("id"))) e.put("action_trace", trace);
                }
            }
            w.remove("decisions");
            update(worldId, w);
        }
        return w;
    }
    @SuppressWarnings("unchecked")
    public Map<String, Object> execution(String worldId, String requestId) {
        var rows = jdbc.queryForList("SELECT receipt FROM action_executions WHERE world_id = ? AND request_id = ?",
                String.class, worldId, requestId);
        return rows.isEmpty() ? null : mapper.readValue(rows.get(0), Map.class);
    }
    public void saveExecution(String worldId, String requestId, Map<String, Object> receipt) {
        jdbc.update("INSERT INTO action_executions(world_id, request_id, receipt) VALUES (?, ?, ?)",
                worldId, requestId, mapper.writeValueAsString(receipt));
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
