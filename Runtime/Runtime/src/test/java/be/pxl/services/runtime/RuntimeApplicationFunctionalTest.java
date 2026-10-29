package be.pxl.services.runtime;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;

import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest
class RuntimeApplicationFunctionalTest {

	@Autowired
	private Environment environment;

	@Test
	@DisplayName("Functional: Runtime environment configuration is active and resolvable")
	void environmentIsConfiguredAndResolvable() {
		assertNotNull(environment, "Spring Environment must be available for runtime functional execution");
		assertNotNull(environment.getSystemProperties(), "System properties must be accessible");
	}

}
