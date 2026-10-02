package org.novelworld.world;

import java.util.Map;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.server.ResponseStatusException;
import tools.jackson.databind.ObjectMapper;

@RestControllerAdvice
public class ApiErrors {
    private final ObjectMapper mapper;
    public ApiErrors(ObjectMapper mapper) { this.mapper = mapper; }
    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<Map<String, String>> invalid(IllegalArgumentException e) { return ResponseEntity.badRequest().body(Map.of("detail", e.getMessage())); }
    @ExceptionHandler(ResponseStatusException.class)
    public ResponseEntity<Map<String, String>> remote(ResponseStatusException e) {
        String message = e.getReason() == null ? "请求失败" : e.getReason();
        try { Object detail = mapper.readValue(message, Map.class).get("detail"); if (detail instanceof String s) message = s; }
        catch (RuntimeException ignored) { }
        return ResponseEntity.status(e.getStatusCode()).body(Map.of("detail", message));
    }
}
