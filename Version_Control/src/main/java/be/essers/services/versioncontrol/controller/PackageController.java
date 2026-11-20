package be.essers.services.versioncontrol.controller;

import be.essers.services.versioncontrol.domain.dto.MappingPackageOverviewDto;
import be.essers.services.versioncontrol.domain.dto.PackageVersionDto;
import be.essers.services.versioncontrol.domain.dto.SetActivePackageRequest;
import be.essers.services.versioncontrol.service.PackageStorageService;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@RestController
@RequestMapping({"/packages", "/Packages"})
public class PackageController {

    private static final int MAX_LENGTH = 20;
    private final PackageStorageService packageStorageService;

    public PackageController(PackageStorageService packageStorageService) {
        this.packageStorageService = packageStorageService;
    }

    @GetMapping
    public ResponseEntity<List<MappingPackageOverviewDto>> getPackages(
            @RequestParam(required = false) String company
    ) {
        if (company != null) {
            validateParam("company", company);
        }
        List<MappingPackageOverviewDto> packages = packageStorageService.listPackages(company);
        return ResponseEntity.ok(packages);
    }

    @GetMapping("/versions")
    public ResponseEntity<List<PackageVersionDto>> getVersions(
            @RequestParam String company,
            @RequestParam String packageType
    ) {
        validateParam("company", company);
        validateParam("packageType", packageType);
        return ResponseEntity.ok(packageStorageService.listVersions(company, packageType));
    }

    @PutMapping("/active")
    public ResponseEntity<MappingPackageOverviewDto> setActivePackage(
            @RequestParam(required = false) String company,
            @RequestParam(required = false) String packageType,
            @RequestParam(required = false) String version,
            @RequestParam(required = false) String user,
            @RequestBody(required = false) SetActivePackageRequest request
    ) {
        String effectiveCompany = request != null && request.company() != null ? request.company() : company;
        String effectiveType = request != null && request.packageType() != null ? request.packageType() : packageType;
        String effectiveVersion = request != null && request.version() != null ? request.version() : version;
        String effectiveUser = request != null && request.user() != null ? request.user() : user;

        validateParam("company", effectiveCompany);
        validateParam("packageType", effectiveType);
        validateParam("version", effectiveVersion);

        MappingPackageOverviewDto updated = packageStorageService.setActivePackage(
                effectiveCompany, effectiveType, effectiveVersion, effectiveUser
        );
        return ResponseEntity.ok(updated);
    }

    private void validateParam(String name, String value) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(name + " parameter must not be empty");
        }
        if (value.length() > MAX_LENGTH) {
            throw new IllegalArgumentException(name + " parameter must not exceed " + MAX_LENGTH + " characters");
        }
    }
}
