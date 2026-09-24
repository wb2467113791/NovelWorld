package org.novelworld.world;

import java.nio.file.Files;
import java.nio.file.Path;
import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ResponseBody;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.servlet.config.annotation.ResourceHandlerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

/** 开发时从 web/dist 服务前端；部署时可用环境变量指定构建目录。 */
@Controller
public class WebAssetsConfig implements WebMvcConfigurer {
    private final Path dist;

    public WebAssetsConfig() {
        String configured = System.getenv("NOVELWORLD_WEB_DIST");
        if (configured != null && !configured.isBlank()) {
            dist = Path.of(configured).toAbsolutePath();
        } else {
            Path fromRoot = Path.of("web", "dist").toAbsolutePath();
            dist = Files.isDirectory(fromRoot) ? fromRoot : Path.of("..", "web", "dist").toAbsolutePath();
        }
    }

    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/assets/**").addResourceLocations(dist.resolve("assets").toUri().toString());
    }

    @GetMapping("/")
    @ResponseBody
    public Resource home() {
        Path index = dist.resolve("index.html");
        if (!Files.isRegularFile(index))
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "请先在 web 目录运行 npm run build");
        return new FileSystemResource(index);
    }
}
