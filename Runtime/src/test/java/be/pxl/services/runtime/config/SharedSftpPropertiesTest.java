package be.pxl.services.runtime.config;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SharedSftpPropertiesTest {

    private static SharedSftpProperties withPort(int port) {
        return new SharedSftpProperties("sftp-shared", port, "shareduser", "secret", "/Packages", false, 5000, 4);
    }

    @Test
    @DisplayName("TC-52-03 the password is never shown in toString()")
    void toStringHidesPassword() {
        String text = withPort(2022).toString();

        assertFalse(text.contains("secret"));
        assertTrue(text.contains("password=****"));
        assertTrue(text.contains("host=sftp-shared"));
    }

    @Test
    @DisplayName("TC-52-03 port 1 and 65535 are kept, 0 and 65536 fall back to the default port")
    void portBoundaries() {
        assertEquals(1, withPort(1).port());
        assertEquals(65_535, withPort(65_535).port());
        assertEquals(SharedSftpProperties.DEFAULT_PORT, withPort(0).port());
        assertEquals(SharedSftpProperties.DEFAULT_PORT, withPort(65_536).port());
    }

    @Test
    @DisplayName("TC-52-03 settings that are not filled in get the defaults")
    void emptySettingsGetDefaults() {
        SharedSftpProperties properties = new SharedSftpProperties(null, 0, " ", null, "", true, 0, 0);

        assertEquals(SharedSftpProperties.DEFAULT_HOST, properties.host());
        assertEquals(SharedSftpProperties.DEFAULT_PORT, properties.port());
        assertEquals(SharedSftpProperties.DEFAULT_USER, properties.user());
        assertEquals("", properties.password());
        assertEquals(SharedSftpProperties.DEFAULT_PACKAGES_PATH, properties.packagesPath());
        assertEquals(SharedSftpProperties.DEFAULT_TIMEOUT_MS, properties.timeoutMs());
        assertEquals(SharedSftpProperties.DEFAULT_POOL_SIZE, properties.poolSize());
    }
}
