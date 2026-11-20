package be.essers.services.versioncontrol.controller;

import be.essers.services.versioncontrol.domain.dto.MappingPackageOverviewDto;
import be.essers.services.versioncontrol.service.PackageStorageService;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

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
            if (company.isBlank()) {
                throw new IllegalArgumentException("Company parameter must not be empty");
            }
            if (company.length() > MAX_LENGTH) {
                throw new IllegalArgumentException("Company parameter must not exceed " + MAX_LENGTH + " characters");
            }
        }
        List<MappingPackageOverviewDto> packages = packageStorageService.listPackages(company);
        return ResponseEntity.ok(packages);
    }

}