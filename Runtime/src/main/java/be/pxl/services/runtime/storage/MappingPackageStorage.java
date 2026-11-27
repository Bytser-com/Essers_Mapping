package be.pxl.services.runtime.storage;

import be.pxl.services.runtime.domain.ActiveMappingPackage;

/**
 * Storage contract for reading mapping packages from {@code sftp-shared}.
 */
public interface MappingPackageStorage {

    /**
     * Return the active mapping package of a customer for one package type (e.g. "inbound").
     * The active version is the one in {@code active.json}, or the newest version when
     * {@code active.json} has no valid entry for that type (same rule as Version Control).
     *
     * @throws be.pxl.services.runtime.exception.MappingPackageNotFoundException when the customer has no package of this type
     * @throws be.pxl.services.runtime.exception.SharedStorageException          when the SFTP storage cannot be read
     * @throws IllegalArgumentException                                           when a parameter is empty or not a valid folder name
     */
    ActiveMappingPackage getActivePackage(String customer, String packageType);
}
