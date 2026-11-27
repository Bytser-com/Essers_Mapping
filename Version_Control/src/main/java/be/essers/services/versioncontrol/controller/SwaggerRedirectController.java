package be.essers.services.versioncontrol.controller;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
@ConditionalOnProperty(name = "springdoc.swagger-ui.enabled", havingValue = "true", matchIfMissing = true)
public class SwaggerRedirectController {

    @GetMapping("/swagger")
    public String redirectSwagger() {
        return "redirect:/docs";
    }
}
