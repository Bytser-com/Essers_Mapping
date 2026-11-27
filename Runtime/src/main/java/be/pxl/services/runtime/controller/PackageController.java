package be.pxl.services.runtime.controller;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import be.pxl.services.runtime.domain.ActiveMappingPackage;
import be.pxl.services.runtime.storage.MappingPackageStorage;

/**
 * REST access to the mapping packages on {@code sftp-shared}.
 */
@RestController
@RequestMapping("/packages")
public class PackageController {

    // Same limit as the company parameter in Version_Control
    private static final int MAX_LENGTH = 20;

    private final MappingPackageStorage mappingPackageStorage;

    public PackageController(MappingPackageStorage mappingPackageStorage) {
        this.mappingPackageStorage = mappingPackageStorage;
    }

    /**
     * Story IT2627T06-52: the active mapping package of a customer for one package type.
     * Example: {@code GET /packages/active?customer=nouryon&packageType=inbound}
     */
    @GetMapping("/active")
    public ResponseEntity<ActiveMappingPackage> getActivePackage(
            @RequestParam String customer,
            @RequestParam String packageType
    ) {
        validateParam("customer", customer);
        validateParam("packageType", packageType);
        return ResponseEntity.ok(mappingPackageStorage.getActivePackage(customer, packageType));
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
