package be.essers.services.versioncontrol.controller;

import be.essers.services.versioncontrol.domain.dto.MappingPackageOverviewDto;
import be.essers.services.versioncontrol.exception.EntityNotFoundException;
import be.essers.services.versioncontrol.exception.GlobalExceptionHandler;
import be.essers.services.versioncontrol.exception.StorageException;
import be.essers.services.versioncontrol.service.PackageStorageService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import java.util.List;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(MockitoExtension.class)
class PackageControllerTest {

    private MockMvc mockMvc;

    @Mock
    private PackageStorageService packageStorageService;

    @InjectMocks
    private PackageController packageController;

    @BeforeEach
    void setUp() {
        mockMvc = MockMvcBuilders.standaloneSetup(packageController)
                .setControllerAdvice(new GlobalExceptionHandler())
                .build();
    }

    @Test
    @DisplayName("GET /packages returns HTTP 200 with the latest package per company and packageType")
    void getAllPackages_returnsList() throws Exception {
        MappingPackageOverviewDto p1 = new MappingPackageOverviewDto(
                "brevalis", "v1", "2025-07-15T12:00:00Z", "analist_b", "Brevalis", "outbound"
        );
        MappingPackageOverviewDto p2 = new MappingPackageOverviewDto(
                "nouryon", "v2", "2026-11-12T10:00:00Z", "analist_a", "Nouryon", "inbound"
        );

        when(packageStorageService.listPackages(null)).thenReturn(List.of(p1, p2));

        mockMvc.perform(get("/packages")
                        .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(2))
                .andExpect(jsonPath("$[0].company").value("brevalis"))
                .andExpect(jsonPath("$[0].latestVersion").value("v1"))
                .andExpect(jsonPath("$[0].createdAt").value("2025-07-15T12:00:00Z"))
                .andExpect(jsonPath("$[0].createdBy").value("analist_b"))
                .andExpect(jsonPath("$[0].customerName").value("Brevalis"))
                .andExpect(jsonPath("$[0].packageType").value("outbound"))
                .andExpect(jsonPath("$[1].company").value("nouryon"))
                .andExpect(jsonPath("$[1].latestVersion").value("v2"))
                .andExpect(jsonPath("$[1].createdAt").value("2026-11-12T10:00:00Z"))
                .andExpect(jsonPath("$[1].createdBy").value("analist_a"))
                .andExpect(jsonPath("$[1].customerName").value("Nouryon"))
                .andExpect(jsonPath("$[1].packageType").value("inbound"));
    }

    @Test
    @DisplayName("GET /Packages (capitalized) maps correctly")
    void getPackages_capitalizedPath_returnsList() throws Exception {
        MappingPackageOverviewDto p1 = new MappingPackageOverviewDto(
                "nouryon", "v2", "2026-11-12T10:00:00Z", "analist_a", "Nouryon", "inbound"
        );

        when(packageStorageService.listPackages(null)).thenReturn(List.of(p1));

        mockMvc.perform(get("/Packages")
                        .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].company").value("nouryon"))
                .andExpect(jsonPath("$[0].packageType").value("inbound"));
    }

    @Test
    @DisplayName("GET /packages lists a company once per packageType")
    void getPackages_companyWithMultipleTypes_returnsOneRowPerType() throws Exception {
        MappingPackageOverviewDto inbound = new MappingPackageOverviewDto(
                "nouryon", "v2", "2026-11-12T10:00:00Z", "analist_a", "Nouryon", "inbound"
        );
        MappingPackageOverviewDto outbound = new MappingPackageOverviewDto(
                "nouryon", "v1", "2026-10-02T10:00:00Z", "analist_b", "Nouryon", "outbound"
        );

        when(packageStorageService.listPackages(null)).thenReturn(List.of(inbound, outbound));

        mockMvc.perform(get("/packages")
                        .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(2))
                .andExpect(jsonPath("$[0].company").value("nouryon"))
                .andExpect(jsonPath("$[0].packageType").value("inbound"))
                .andExpect(jsonPath("$[0].latestVersion").value("v2"))
                .andExpect(jsonPath("$[1].company").value("nouryon"))
                .andExpect(jsonPath("$[1].packageType").value("outbound"))
                .andExpect(jsonPath("$[1].latestVersion").value("v1"));
    }

    @Test
    @DisplayName("GET /packages?company=nouryon filters by company")
    void getPackages_filteredByCompany_returnsCompanyPackages() throws Exception {
        MappingPackageOverviewDto p1 = new MappingPackageOverviewDto(
                "nouryon", "v2", "2026-11-12T10:00:00Z", "analist_a", "Nouryon", "inbound"
        );

        when(packageStorageService.listPackages("nouryon")).thenReturn(List.of(p1));

        mockMvc.perform(get("/packages")
                        .param("company", "nouryon")
                        .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(1))
                .andExpect(jsonPath("$[0].company").value("nouryon"))
                .andExpect(jsonPath("$[0].latestVersion").value("v2"))
                .andExpect(jsonPath("$[0].packageType").value("inbound"));
    }

    @Test
    @DisplayName("GET /packages sends null for metadata that is missing")
    void getPackages_missingMetadata_returnsNullFields() throws Exception {
        MappingPackageOverviewDto p1 = new MappingPackageOverviewDto(
                "nouryon", "v1", "2026-11-10T12:00:00Z", null, null, "inbound"
        );

        when(packageStorageService.listPackages(null)).thenReturn(List.of(p1));

        mockMvc.perform(get("/packages")
                        .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].company").value("nouryon"))
                .andExpect(jsonPath("$[0].createdBy").isEmpty())
                .andExpect(jsonPath("$[0].customerName").isEmpty());
    }

    @Test
    @DisplayName("GET /packages without packages returns HTTP 200 with an empty list")
    void getPackages_noPackages_returnsEmptyList() throws Exception {
        when(packageStorageService.listPackages(null)).thenReturn(List.of());

        mockMvc.perform(get("/packages")
                        .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(0));
    }

    @Test
    @DisplayName("GET /packages with blank company parameter returns 400")
    void getPackages_blankCompany_returns400() throws Exception {
        mockMvc.perform(get("/packages")
                        .param("company", "   ")
                        .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.title").value("Invalid Request Parameter"));

        verify(packageStorageService, never()).listPackages(any());
    }

    @Test
    @DisplayName("GET /packages with a company of more than 20 characters returns 400")
    void getPackages_tooLongCompany_returns400() throws Exception {
        mockMvc.perform(get("/packages")
                        .param("company", "abcdefghijklmnopqrstu")
                        .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.title").value("Invalid Request Parameter"));

        verify(packageStorageService, never()).listPackages(any());
    }

    @Test
    @DisplayName("GET /packages with a company of exactly 20 characters is accepted")
    void getPackages_companyOfMaxLength_returns200() throws Exception {
        when(packageStorageService.listPackages("abcdefghijklmnopqrst")).thenReturn(List.of());

        mockMvc.perform(get("/packages")
                        .param("company", "abcdefghijklmnopqrst")
                        .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk());
    }

    @Test
    @DisplayName("GET /packages with path traversal characters returns 400")
    void getPackages_pathTraversal_returns400() throws Exception {
        when(packageStorageService.listPackages("../etc"))
                .thenThrow(new IllegalArgumentException("Path segment contains illegal characters: ../etc"));

        mockMvc.perform(get("/packages")
                        .param("company", "../etc")
                        .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.title").value("Invalid Request Parameter"));
    }

    @Test
    @DisplayName("GET /packages?company with unknown company returns 404")
    void getPackages_unknownCompany_returns404() throws Exception {
        when(packageStorageService.listPackages("NonExisting"))
                .thenThrow(new EntityNotFoundException("Company directory 'NonExisting' does not exist at /Packages"));

        mockMvc.perform(get("/packages")
                        .param("company", "NonExisting")
                        .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.title").value("Entity Not Found"));
    }

    @Test
    @DisplayName("GET /packages returns 502 when the SFTP server cannot be reached")
    void getPackages_sftpUnreachable_returns502() throws Exception {
        when(packageStorageService.listPackages(null))
                .thenThrow(new StorageException("Unable to read packages from SFTP storage: connection refused"));

        mockMvc.perform(get("/packages")
                        .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isBadGateway())
                .andExpect(jsonPath("$.title").value("SFTP Storage Error"));
    }

    @Test
    @DisplayName("GET /packages/versions returns list of package versions")
    void getVersions_returnsList() throws Exception {
        var v1 = new be.essers.services.versioncontrol.domain.dto.PackageVersionDto("v1", true, "2024-06-19T12:00:00Z", "analist_a", "Initial");
        var v2 = new be.essers.services.versioncontrol.domain.dto.PackageVersionDto("v2", false, "2024-07-20T12:00:00Z", "analist_b", "Update");

        when(packageStorageService.listVersions("nouryon", "inbound")).thenReturn(List.of(v1, v2));

        mockMvc.perform(get("/packages/versions")
                        .param("company", "nouryon")
                        .param("packageType", "inbound")
                        .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(2))
                .andExpect(jsonPath("$[0].version").value("v1"))
                .andExpect(jsonPath("$[0].isActive").value(true))
                .andExpect(jsonPath("$[1].version").value("v2"))
                .andExpect(jsonPath("$[1].isActive").value(false));
    }

    @Test
    @DisplayName("PUT /packages/active updates active package and returns 200")
    void setActivePackage_returnsUpdatedDto() throws Exception {
        MappingPackageOverviewDto updated = new MappingPackageOverviewDto(
                "nouryon", "v2", "2024-06-19T12:00:00Z", "analist_a", "Nouryon", "inbound", "v1", "2024-08-01T15:00:00Z", "lead_analyst"
        );

        when(packageStorageService.setActivePackage("nouryon", "inbound", "v1", "lead_analyst"))
                .thenReturn(updated);

        mockMvc.perform(put("/packages/active")
                        .param("company", "nouryon")
                        .param("packageType", "inbound")
                        .param("version", "v1")
                        .param("user", "lead_analyst")
                        .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.company").value("nouryon"))
                .andExpect(jsonPath("$.activeVersion").value("v1"))
                .andExpect(jsonPath("$.latestVersion").value("v2"))
                .andExpect(jsonPath("$.activeUpdatedBy").value("lead_analyst"));
    }
}
