package be.essers.services.versioncontrol.config;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.env.EnvironmentPostProcessor;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.MapPropertySource;

import java.util.HashMap;
import java.util.Map;

/**
 * Ensures Swagger / OpenAPI documentation is governed solely by ENVIRONMENT:
 * enabled in development and testing, and disabled in staging and production.
 */
public class SwaggerEnvironmentPostProcessor implements EnvironmentPostProcessor {

    @Override
    public void postProcessEnvironment(ConfigurableEnvironment environment, SpringApplication application) {
        String env = environment.getProperty("ENVIRONMENT", "").trim().toLowerCase();
        String swaggerOverride = environment.getProperty("SWAGGER_ENABLED", "").trim().toLowerCase();

        boolean isBlocked = "staging".equals(env) || "stage".equals(env)
                || "production".equals(env) || "prod".equals(env)
                || "false".equals(swaggerOverride) || "0".equals(swaggerOverride) || "no".equals(swaggerOverride) || "off".equals(swaggerOverride);

        boolean isAllowed = !isBlocked && (
                env.isEmpty() || "development".equals(env) || "dev".equals(env) || "local".equals(env)
                || "testing".equals(env) || "test".equals(env)
                || "true".equals(swaggerOverride) || "1".equals(swaggerOverride) || "yes".equals(swaggerOverride) || "on".equals(swaggerOverride)
        );

        boolean enabled = !isBlocked && isAllowed;

        Map<String, Object> props = new HashMap<>();
        props.put("springdoc.swagger-ui.path", "/docs");
        props.put("springdoc.swagger-ui.enabled", String.valueOf(enabled));
        props.put("springdoc.api-docs.enabled", String.valueOf(enabled));

        environment.getPropertySources().addFirst(new MapPropertySource("swaggerDynamicProperties", props));
    }
}
