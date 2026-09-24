package org.novelworld.world;

import java.util.Map;
import java.time.Duration;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestClientResponseException;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.server.ResponseStatusException;

/** Spring Boot 仅向本机内部 Agent Runtime 发送调度指令。 */
@Component
public class AgentRuntimeClient {
    private final RestClient client;

    public AgentRuntimeClient(@Value("${novelworld.agent.url:http://127.0.0.1:8001}") String url) {
        var requests = new SimpleClientHttpRequestFactory();
        requests.setConnectTimeout(Duration.ofSeconds(3));
        requests.setReadTimeout(Duration.ofSeconds(10));
        this.client = RestClient.builder().baseUrl(url).requestFactory(requests).build();
    }

    @SuppressWarnings("unchecked")
    public Map<String, Object> status() {
        try {
            return client.get().uri("/internal/status").retrieve().body(Map.class);
        } catch (RestClientException error) {
            throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE, "Python Agent Runtime 不可用", error);
        }
    }

    @SuppressWarnings("unchecked")
    public Map<String, Object> control(String action, Map<String, Object> body) {
        try {
            return client.post().uri("/internal/control/" + action).body(body).retrieve().body(Map.class);
        } catch (RestClientResponseException error) {
            throw new ResponseStatusException(error.getStatusCode(), error.getResponseBodyAsString(), error);
        } catch (RestClientException error) {
            throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE, "Python Agent Runtime 不可用", error);
        }
    }
}
