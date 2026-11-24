package be.essers.services.versioncontrol.controller;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.context.WebApplicationContext;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
class SwaggerEndpointTest {

    @Autowired
    private WebApplicationContext context;

    @Test
    @DisplayName("Swagger endpoints respond in default/development environment")
    void swaggerAvailableInDevelopment() throws Exception {
        MockMvc mvc = MockMvcBuilders.webAppContextSetup(context).build();
        mvc.perform(get("/swagger"))
                .andExpect(status().is3xxRedirection())
                .andExpect(header().string("Location", "/docs"));
    }

    @Nested
    @SpringBootTest
    @TestPropertySource(properties = "ENVIRONMENT=production")
    class ProductionSwaggerTest {
        @Autowired
        private WebApplicationContext context;

        @Test
        @DisplayName("Swagger endpoints return 404 when ENVIRONMENT is production")
        void swaggerDisabledInProduction() throws Exception {
            MockMvc mvc = MockMvcBuilders.webAppContextSetup(context).build();
            mvc.perform(get("/swagger")).andExpect(status().isNotFound());
            mvc.perform(get("/docs")).andExpect(status().isNotFound());
            mvc.perform(get("/v3/api-docs")).andExpect(status().isNotFound());
        }
    }

    @Nested
    @SpringBootTest
    @TestPropertySource(properties = "ENVIRONMENT=staging")
    class StagingSwaggerTest {
        @Autowired
        private WebApplicationContext context;

        @Test
        @DisplayName("Swagger endpoints return 404 when ENVIRONMENT is staging")
        void swaggerDisabledInStaging() throws Exception {
            MockMvc mvc = MockMvcBuilders.webAppContextSetup(context).build();
            mvc.perform(get("/swagger")).andExpect(status().isNotFound());
            mvc.perform(get("/docs")).andExpect(status().isNotFound());
            mvc.perform(get("/v3/api-docs")).andExpect(status().isNotFound());
        }
    }
}
