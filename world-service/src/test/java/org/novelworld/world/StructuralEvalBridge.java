package org.novelworld.world;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import org.h2.jdbcx.JdbcConnectionPool;
import org.springframework.jdbc.core.JdbcTemplate;
import tools.jackson.databind.ObjectMapper;

/** Offline eval transport only: calls production MCP handlers/rules against temporary H2. */
public final class StructuralEvalBridge {
    public static void main(String[] args) throws Exception {
        var pool = JdbcConnectionPool.create(args[0], "sa", "");
        var jdbc = new JdbcTemplate(pool);
        jdbc.execute("CREATE TABLE IF NOT EXISTS world_saves (world_id VARCHAR(64) PRIMARY KEY, snapshot CLOB NOT NULL, revision BIGINT NOT NULL)");
        var mapper = new ObjectMapper();
        var tools = new WorldMcpTools(new WorldStore(jdbc, mapper), new WorldRules(), mapper);
        System.out.println("READY");
        try (var reader = new BufferedReader(new InputStreamReader(System.in, StandardCharsets.UTF_8))) {
            String line;
            while ((line = reader.readLine()) != null) {
                try {
                    var request = mapper.readValue(line, Map.class);
                    var a = WorldObjects.map(request.get("arguments"));
                    String id = (String) a.get("worldId");
                    String output = switch ((String) request.get("name")) {
                        case "create_world" -> tools.createWorld((String) a.get("snapshotJson"));
                        case "get_world" -> tools.getWorld(id);
                        case "get_world_events" -> tools.getWorldEvents(id, ((Number) a.get("afterIndex")).intValue());
                        case "execute_world_tool" -> tools.executeWorldTool(id, (String) a.get("name"),
                                (String) a.get("argumentsJson"), (String) a.get("actingCharacter"));
                        case "save_agent_state" -> tools.saveAgentState(id, (String) a.get("agentStateJson"));
                        case "advance_world_time" -> tools.advanceWorldTime(id, ((Number) a.get("minutes")).intValue());
                        case "introduce_narrative_event" -> tools.introduceNarrativeEvent(id, (String) a.get("category"),
                                (String) a.get("location"), (String) a.get("observation"),
                                ((Number) a.get("tickCount")).intValue(), (String) a.get("form"));
                        default -> throw new IllegalArgumentException("Unsupported eval command");
                    };
                    System.out.println(mapper.writeValueAsString(Map.of("output", output)));
                } catch (Exception error) {
                    System.out.println(mapper.writeValueAsString(Map.of("error", String.valueOf(error.getMessage()))));
                }
            }
        } finally {
            jdbc.execute("SHUTDOWN");
            pool.dispose();
        }
    }
}
