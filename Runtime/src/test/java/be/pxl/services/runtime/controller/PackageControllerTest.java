package be.pxl.services.runtime.controller;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

import be.pxl.services.runtime.domain.ActiveMappingPackage;
import be.pxl.services.runtime.exception.GlobalExceptionHandler;
import be.pxl.services.runtime.exception.MappingPackageNotFoundException;
import be.pxl.services.runtime.exception.SharedStorageException;
import be.pxl.services.runtime.storage.MappingPackageStorage;

import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class PackageControllerTest {

    private MappingPackageStorage mappingPackageStorage;
    private MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        mappingPackageStorage = mock(MappingPackageStorage.class);
        mockMvc = MockMvcBuilders.standaloneSetup(new PackageController(mappingPackageStorage))
                .setControllerAdvice(new GlobalExceptionHandler())
                .build();
    }

    @Test
    @DisplayName("TC-52-01 GET /packages/active returns HTTP 200 with the active package")
    void getActivePackageReturnsActivePackage() throws Exception {
        when(mappingPackageStorage.getActivePackage("nouryon", "inbound")).thenReturn(nouryonInboundV2());

        mockMvc.perform(get("/packages/active").param("customer", "nouryon").param("packageType", "inbound"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.customer").value("nouryon"))
                .andExpect(jsonPath("$.packageType").value("inbound"))
                .andExpect(jsonPath("$.version").value("v2"))
                .andExpect(jsonPath("$.status").value("ACTIVE"))
                .andExpect(jsonPath("$.mappingPackage.meta.client_name").value("nouryon"));
    }

    @Test
    @DisplayName("GET /packages/active without a package returns HTTP 404")
    void getActivePackageWithoutPackageReturns404() throws Exception {
        when(mappingPackageStorage.getActivePackage("onbekendeklant123", "inbound"))
                .thenThrow(new MappingPackageNotFoundException("No mapping packages found for customer 'onbekendeklant123'"));

        mockMvc.perform(get("/packages/active").param("customer", "onbekendeklant123").param("packageType", "inbound"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.status").value(404));
    }

    @Test
    @DisplayName("GET /packages/active without packageType returns HTTP 400")
    void getActivePackageWithoutTypeReturns400() throws Exception {
        mockMvc.perform(get("/packages/active").param("customer", "nouryon"))
                .andExpect(status().isBadRequest());

        verify(mappingPackageStorage, never()).getActivePackage(anyString(), anyString());
    }

    @Test
    @DisplayName("GET /packages/active with a customer name that is too long returns HTTP 400")
    void getActivePackageWithTooLongCustomerReturns400() throws Exception {
        mockMvc.perform(get("/packages/active").param("customer", "a".repeat(21)).param("packageType", "inbound"))
                .andExpect(status().isBadRequest());

        verify(mappingPackageStorage, never()).getActivePackage(anyString(), anyString());
    }

    @Test
    @DisplayName("GET /packages/active returns HTTP 502 when the SFTP server cannot be reached")
    void getActivePackageWithSftpDownReturns502() throws Exception {
        when(mappingPackageStorage.getActivePackage("nouryon", "inbound"))
                .thenThrow(new SharedStorageException("Failed to read mapping packages of nouryon under /Packages"));

        mockMvc.perform(get("/packages/active").param("customer", "nouryon").param("packageType", "inbound"))
                .andExpect(status().isBadGateway());
    }

    private ActiveMappingPackage nouryonInboundV2() {
        JsonNode mappingPackage = new ObjectMapper().readTree("""
                { "meta": { "client_name": "nouryon", "package_type": "inbound" }, "mappings": [] }
                """);
        return new ActiveMappingPackage("nouryon", "inbound", "v2", ActiveMappingPackage.STATUS_ACTIVE,
                "2026-11-20T10:00:00Z", "lead_analyst", mappingPackage);
    }
}
