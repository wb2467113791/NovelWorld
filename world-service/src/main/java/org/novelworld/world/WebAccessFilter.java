package org.novelworld.world;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Base64;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

/** 可选的本机单用户浏览器认证；MCP 通道由本机绑定隔离。 */
@Component
public class WebAccessFilter extends OncePerRequestFilter {
    private final String username;
    private final String password;

    public WebAccessFilter(@Value("${novelworld.web.user:author}") String username,
                           @Value("${novelworld.web.password:}") String password) {
        this.username = username;
        this.password = password;
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        String path = request.getRequestURI();
        return password.isBlank() || !("/".equals(path) || path.startsWith("/api/") || path.startsWith("/assets/"));
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response,
                                    FilterChain chain) throws ServletException, IOException {
        String authorization = request.getHeader("Authorization");
        boolean allowed = false;
        if (authorization != null && authorization.startsWith("Basic ")) {
            try {
                String credentials = new String(Base64.getDecoder().decode(authorization.substring(6)), StandardCharsets.UTF_8);
                int separator = credentials.indexOf(':');
                if (separator >= 0) {
                    allowed = MessageDigest.isEqual(credentials.substring(0, separator).getBytes(StandardCharsets.UTF_8),
                                                    username.getBytes(StandardCharsets.UTF_8))
                            && MessageDigest.isEqual(credentials.substring(separator + 1).getBytes(StandardCharsets.UTF_8),
                                                     password.getBytes(StandardCharsets.UTF_8));
                }
            } catch (IllegalArgumentException ignored) {
                // 无效 Basic 编码按未认证处理。
            }
        }
        if (!allowed) {
            response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
            response.setHeader("WWW-Authenticate", "Basic realm=\"NovelWorld\"");
            return;
        }
        chain.doFilter(request, response);
    }
}
