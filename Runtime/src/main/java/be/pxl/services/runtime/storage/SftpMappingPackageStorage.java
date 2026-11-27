package be.pxl.services.runtime.storage;

import java.io.ByteArrayOutputStream;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.apache.sshd.sftp.client.SftpClient;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.sftp.session.SftpRemoteFileTemplate;
import org.springframework.stereotype.Service;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

import be.pxl.services.runtime.config.SharedSftpConfig;
import be.pxl.services.runtime.config.SharedSftpProperties;
import be.pxl.services.runtime.domain.ActiveMappingPackage;
import be.pxl.services.runtime.domain.ActivePackageInfo;
import be.pxl.services.runtime.exception.MappingPackageNotFoundException;
import be.pxl.services.runtime.exception.SharedStorageException;

/**
 * SFTP-backed implementation of {@link MappingPackageStorage}.
 *
 * <p>Layout under {@code sftp.shared.packages-path} (same as Version_Control):
 * {@code /Packages/<customer>/active.json} and {@code /Packages/<customer>/<version>/<type>/MPackage.json}
 */
@Service
public class SftpMappingPackageStorage implements MappingPackageStorage {

    private static final Logger LOGGER = LoggerFactory.getLogger(SftpMappingPackageStorage.class);
    private static final String PACKAGE_FILENAME = "MPackage.json";
    private static final String ACTIVE_FILENAME = "active.json";

    // Newest version first: v10 before v9 before v1
    private static final Comparator<String> NEWEST_VERSION_FIRST = Comparator
            .comparingInt(SftpMappingPackageStorage::versionNumber).reversed()
            .thenComparing(Comparator.reverseOrder());

    private final SftpRemoteFileTemplate sftpTemplate;
    private final String packagesRoot;
    private final ObjectMapper objectMapper;

    @Autowired
    public SftpMappingPackageStorage(
            @Qualifier(SharedSftpConfig.SHARED_SFTP_TEMPLATE) SftpRemoteFileTemplate sftpTemplate,
            SharedSftpProperties sftpProperties,
            ObjectMapper objectMapper
    ) {
        this.sftpTemplate = sftpTemplate;
        this.packagesRoot = sftpProperties.packagesPath();
        this.objectMapper = objectMapper;
    }

    @Override
    public ActiveMappingPackage getActivePackage(String customer, String packageType) {
        String customerName = requireSafeSegment("customer", customer);
        String type = requireSafeSegment("packageType", packageType).toLowerCase();

        try {
            String customerFolder = findSubdirectory(packagesRoot, customerName);
            if (customerFolder == null) {
                throw new MappingPackageNotFoundException("No mapping packages found for customer '" + customerName + "'");
            }
            String customerPath = packagesRoot + "/" + customerFolder;

            // All versions with a package of this type, newest first: version -> type folder path
            Map<String, String> typePathByVersion = findVersionsWithType(customerPath, type);
            if (typePathByVersion.isEmpty()) {
                throw new MappingPackageNotFoundException(
                        "No " + type + " mapping package found for customer '" + customerFolder + "'");
            }

            ActivePackageInfo activeInfo = readActivePackages(customerPath).get(type);
            String activeVersion = chooseActiveVersion(activeInfo, typePathByVersion, customerFolder, type);
            JsonNode mappingPackage = readMappingPackage(typePathByVersion.get(activeVersion));

            // Only use the info of active.json when it is about the version that is returned
            boolean fromActiveJson = activeInfo != null && activeVersion.equalsIgnoreCase(activeInfo.version().trim());

            LOGGER.info("Active {} mapping package for {}: {}", type, customerFolder, activeVersion);
            return new ActiveMappingPackage(
                    customerFolder,
                    type,
                    activeVersion,
                    ActiveMappingPackage.STATUS_ACTIVE,
                    fromActiveJson ? activeInfo.updatedAt() : metaValue(mappingPackage, "date_created"),
                    fromActiveJson ? activeInfo.updatedBy() : metaValue(mappingPackage, "user_created"),
                    mappingPackage
            );
        } catch (MappingPackageNotFoundException | SharedStorageException ex) {
            throw ex;
        } catch (Exception ex) {
            throw new SharedStorageException("Failed to read mapping packages of " + customerName + " under " + packagesRoot, ex);
        }
    }

    // The version from active.json when that version really has a package of this type, otherwise the newest version
    private String chooseActiveVersion(ActivePackageInfo activeInfo, Map<String, String> typePathByVersion,
                                       String customer, String type) {
        if (activeInfo != null) {
            for (String version : typePathByVersion.keySet()) {
                if (version.equalsIgnoreCase(activeInfo.version().trim())) {
                    return version;
                }
            }
            LOGGER.warn("active.json of {} points to {} {}, which does not exist; using the newest version",
                    customer, type, activeInfo.version());
        }
        return typePathByVersion.keySet().iterator().next();
    }

    private Map<String, String> findVersionsWithType(String customerPath, String type) {
        List<String> versions = listSubdirectories(customerPath);
        versions.sort(NEWEST_VERSION_FIRST);

        Map<String, String> result = new LinkedHashMap<>();
        for (String version : versions) {
            String versionPath = customerPath + "/" + version;
            String typeFolder = findSubdirectory(versionPath, type);
            if (typeFolder != null) {
                result.put(version, versionPath + "/" + typeFolder);
            }
        }
        return result;
    }

    // Reads active.json as "type -> active version". A missing or broken file gives an empty map.
    private Map<String, ActivePackageInfo> readActivePackages(String customerPath) {
        String activePath = customerPath + "/" + ACTIVE_FILENAME;
        Map<String, ActivePackageInfo> result = new HashMap<>();
        if (!sftpTemplate.exists(activePath)) {
            return result;
        }
        try {
            JsonNode root = objectMapper.readTree(readFile(activePath));
            if (root == null || !root.isObject()) {
                return result;
            }
            // Some files wrap the types in a "types" block; Version_Control accepts both
            JsonNode types = root.has("types") && root.get("types").isObject() ? root.get("types") : root;
            for (var entry : types.properties()) {
                ActivePackageInfo info = objectMapper.treeToValue(entry.getValue(), ActivePackageInfo.class);
                if (info != null && info.version() != null && !info.version().isBlank()) {
                    result.put(entry.getKey().toLowerCase(), info);
                }
            }
        } catch (Exception ex) {
            LOGGER.warn("Failed to read {}: {}", activePath, ex.getMessage());
        }
        return result;
    }

    private JsonNode readMappingPackage(String typePath) {
        String filename = null;
        for (SftpClient.DirEntry entry : listEntries(typePath)) {
            if (PACKAGE_FILENAME.equalsIgnoreCase(entry.getFilename())) {
                filename = entry.getFilename();
            }
        }
        if (filename == null) {
            throw new SharedStorageException(PACKAGE_FILENAME + " is missing in " + typePath);
        }

        String packagePath = typePath + "/" + filename;
        JsonNode node;
        try {
            node = objectMapper.readTree(readFile(packagePath));
        } catch (SharedStorageException ex) {
            throw ex;
        } catch (Exception ex) {
            throw new SharedStorageException(packagePath + " is not valid JSON", ex);
        }
        if (node == null || !node.isObject()) {
            throw new SharedStorageException(packagePath + " is not a JSON object");
        }
        return node;
    }

    private byte[] readFile(String path) {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        boolean success = sftpTemplate.get(path, in -> in.transferTo(out));
        if (!success) {
            throw new SharedStorageException("Failed to read " + path);
        }
        return out.toByteArray();
    }

    // Finds a subdirectory by name, ignoring upper/lower case ("Nouryon" finds "nouryon")
    private String findSubdirectory(String parentPath, String name) {
        for (String folder : listSubdirectories(parentPath)) {
            if (folder.equalsIgnoreCase(name)) {
                return folder;
            }
        }
        return null;
    }

    private List<String> listSubdirectories(String path) {
        List<String> names = new ArrayList<>();
        for (SftpClient.DirEntry entry : listEntries(path)) {
            String name = entry.getFilename();
            if (!".".equals(name) && !"..".equals(name) && entry.getAttributes().isDirectory()) {
                names.add(name);
            }
        }
        return names;
    }

    private SftpClient.DirEntry[] listEntries(String path) {
        if (!sftpTemplate.exists(path)) {
            return new SftpClient.DirEntry[0];
        }
        SftpClient.DirEntry[] entries = sftpTemplate.list(path);
        return entries != null ? entries : new SftpClient.DirEntry[0];
    }

    // A value from the "meta" block of MPackage.json, or null
    private static String metaValue(JsonNode mappingPackage, String field) {
        JsonNode value = mappingPackage.path("meta").path(field);
        return value.isString() ? value.asString() : null;
    }

    // The number in a version folder name: "v3" -> 3. Names without a number sort last.
    private static int versionNumber(String version) {
        String digits = version.replaceFirst("^[vV]", "");
        return digits.matches("\\d+") ? Integer.parseInt(digits) : -1;
    }

    // The value becomes a folder name on SFTP, so it may not contain path characters
    private static String requireSafeSegment(String name, String value) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(name + " must not be empty");
        }
        String trimmed = value.trim();
        if (trimmed.contains("/") || trimmed.contains("\\") || trimmed.contains("..")) {
            throw new IllegalArgumentException(name + " contains illegal characters: " + value);
        }
        return trimmed;
    }
}
