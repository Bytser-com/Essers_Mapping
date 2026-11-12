package be.pxl.services.runtime;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertNotNull;

class RuntimeApplicationTests {

	@Test
	@DisplayName("Unit: RuntimeApplication instance can be constructed")
	void applicationInstanceConstructs() {
		RuntimeApplication app = new RuntimeApplication();
		assertNotNull(app);
	}

	@Test
	@DisplayName("Unit: RuntimeApplication main method starts cleanly")
	void mainMethodRunsWithoutException() {
		assertDoesNotThrow(() -> RuntimeApplication.main(new String[] { "--spring.main.web-application-type=none" }));
	}

}
