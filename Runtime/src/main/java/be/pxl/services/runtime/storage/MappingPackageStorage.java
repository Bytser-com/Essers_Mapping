package be.pxl.services.runtime.storage;

import be.pxl.services.runtime.domain.ActiveMappingPackage;

/**
 * Storage contract for reading mapping packages from {@code sftp-shared}.
 */
public interface MappingPackageStorage {

    // Active version = the one in active.json, or the newest version (same rule as Version Control)
    ActiveMappingPackage getActivePackage(String customer, String packageType);
}
