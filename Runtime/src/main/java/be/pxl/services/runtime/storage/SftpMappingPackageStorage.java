package be.pxl.services.runtime.storage;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

import org.apache.sshd.sftp.client.SftpClient;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.file.remote.session.Session;
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
    private static final int MAX_PACKAGE_BYTES = 10 * 1024 * 1024;
    private static final int MAX_ACTIVE_BYTES = 1024 * 1024;

    // Newest version first: v10 before v9 before v1
    private static final Comparator<String> NEWEST_VERSION_FIRST = Comparator
            .comparingLong(SftpMappingPackageStorage::versionNumber).reversed()
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
        this.packagesRoot = normalizeRoot(sftpProperties.packagesPath());
        this.objectMapper = objectMapper;
    }

    @Override
    public ActiveMappingPackage getActivePackage(String customer, String packageType) {
        String customerName = requireSafeSegment("customer", customer);
        String type = requireSafeSegment("packageType", packageType).toLowerCase(Locale.ROOT);

        try {
            // One SFTP session for all reads of this request
            return sftpTemplate.execute(session -> findActivePackage(session, customerName, type));
        } catch (Exception ex) {
            // The template wraps our own exceptions; give them back unchanged
            for (Throwable cause = ex; cause != null; cause = cause.getCause()) {
                if (cause instanceof MappingPackageNotFoundException notFound) {
                    throw notFound;
                }
                if (cause instanceof SharedStorageException storageError) {
                    throw storageError;
                }
            }
            throw new SharedStorageException("Failed to read mapping packages of " + customerName + " under " + packagesRoot, ex);
        }
    }

    private ActiveMappingPackage findActivePackage(Session<SftpClient.DirEntry> session, String customer, String type)
            throws IOException {
        String customerFolder = findSubdirectory(session, packagesRoot, customer);
        if (customerFolder == null) {
            throw new MappingPackageNotFoundException("No mapping packages found for customer '" + customer + "'");
        }
        String customerPath = packagesRoot + "/" + customerFolder;
        ActivePackageInfo activeInfo = readActivePackages(session, customerPath).get(type);

        // Fast path: the version in active.json, without scanning all version folders
        if (activeInfo != null) {
            String versionFolder = findSubdirectory(session, customerPath, activeInfo.version().trim());
            String packagePath = versionFolder == null ? null : findPackageFile(session, customerPath + "/" + versionFolder, type);
            if (packagePath != null) {
                return toActivePackage(customerFolder, type, versionFolder, activeInfo, readMappingPackage(session, packagePath));
            }
            LOGGER.warn("active.json of {} points to {} {}, which has no package; using the newest version",
                    customerFolder, type, activeInfo.version());
        }

        // No (valid) entry in active.json: the newest version that really has a package of this type
        List<String> versions = listSubdirectories(session, customerPath);
        versions.sort(NEWEST_VERSION_FIRST);
        for (String version : versions) {
            String packagePath = findPackageFile(session, customerPath + "/" + version, type);
            if (packagePath != null) {
                return toActivePackage(customerFolder, type, version, null, readMappingPackage(session, packagePath));
            }
        }
        throw new MappingPackageNotFoundException("No " + type + " mapping package found for customer '" + customerFolder + "'");
    }

    private ActiveMappingPackage toActivePackage(String customer, String type, String version,
                                                 ActivePackageInfo activeInfo, JsonNode mappingPackage) {
        LOGGER.info("Active {} mapping package for {}: {}", type, customer, version);
        // Per field: the info of active.json, otherwise the meta block of MPackage.json (like Version_Control)
        String activatedAt = activeInfo != null && activeInfo.updatedAt() != null
                ? activeInfo.updatedAt() : metaValue(mappingPackage, "date_created");
        String activatedBy = activeInfo != null && activeInfo.updatedBy() != null
                ? activeInfo.updatedBy() : metaValue(mappingPackage, "user_created");
        return new ActiveMappingPackage(customer, type, version, ActiveMappingPackage.STATUS_ACTIVE,
                activatedAt, activatedBy, mappingPackage);
    }

    // Path of MPackage.json in <version>/<type>, or null when that folder or file does not exist
    private String findPackageFile(Session<SftpClient.DirEntry> session, String versionPath, String type) throws IOException {
        String typeFolder = findSubdirectory(session, versionPath, type);
        if (typeFolder == null) {
            return null;
        }
        String typePath = versionPath + "/" + typeFolder;
        for (SftpClient.DirEntry entry : listEntries(session, typePath)) {
            if (PACKAGE_FILENAME.equalsIgnoreCase(entry.getFilename()) && isRegularFile(entry)) {
                return typePath + "/" + entry.getFilename();
            }
        }
        return null;
    }

    // Reads active.json as "type -> active version". SFTP errors are thrown; a broken file or entry is skipped.
    private Map<String, ActivePackageInfo> readActivePackages(Session<SftpClient.DirEntry> session, String customerPath)
            throws IOException {
        String activePath = customerPath + "/" + ACTIVE_FILENAME;
        Map<String, ActivePackageInfo> result = new HashMap<>();
        if (!session.exists(activePath)) {
            return result;
        }
        byte[] content = readFile(session, activePath, MAX_ACTIVE_BYTES);

        JsonNode root;
        try {
            root = objectMapper.readTree(content);
        } catch (Exception ex) {
            LOGGER.warn("{} is not valid JSON, it is ignored: {}", activePath, ex.getMessage());
            return result;
        }
        if (root == null || !root.isObject()) {
            return result;
        }
        // Some files wrap the types in a "types" block; Version_Control accepts both
        JsonNode types = root.has("types") && root.get("types").isObject() ? root.get("types") : root;
        for (var entry : types.properties()) {
            try {
                ActivePackageInfo info = objectMapper.treeToValue(entry.getValue(), ActivePackageInfo.class);
                if (info != null && info.version() != null && !info.version().isBlank()) {
                    result.put(entry.getKey().toLowerCase(Locale.ROOT), info);
                }
            } catch (Exception ex) {
                LOGGER.warn("Entry '{}' in {} is skipped: {}", entry.getKey(), activePath, ex.getMessage());
            }
        }
        return result;
    }

    private JsonNode readMappingPackage(Session<SftpClient.DirEntry> session, String packagePath) throws IOException {
        byte[] content = readFile(session, packagePath, MAX_PACKAGE_BYTES);
        JsonNode node;
        try {
            node = objectMapper.readTree(content);
        } catch (Exception ex) {
            throw new SharedStorageException(packagePath + " is not valid JSON", ex);
        }
        if (node == null || !node.isObject()) {
            throw new SharedStorageException(packagePath + " is not a JSON object");
        }
        return node;
    }

    // Reads a file, but stops at maxBytes so a huge or corrupt file cannot fill the memory
    private byte[] readFile(Session<SftpClient.DirEntry> session, String path, int maxBytes) throws IOException {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        try (InputStream in = session.readRaw(path)) {
            byte[] buffer = new byte[8192];
            int read;
            while ((read = in.read(buffer)) != -1) {
                if (out.size() + read > maxBytes) {
                    throw new SharedStorageException(path + " is larger than " + maxBytes + " bytes");
                }
                out.write(buffer, 0, read);
            }
        } finally {
            session.finalizeRaw();
        }
        return out.toByteArray();
    }

    // Finds a subdirectory by name, ignoring upper/lower case ("Nouryon" finds "nouryon")
    private String findSubdirectory(Session<SftpClient.DirEntry> session, String parentPath, String name) throws IOException {
        for (String folder : listSubdirectories(session, parentPath)) {
            if (folder.equalsIgnoreCase(name)) {
                return folder;
            }
        }
        return null;
    }

    private List<String> listSubdirectories(Session<SftpClient.DirEntry> session, String path) throws IOException {
        List<String> names = new ArrayList<>();
        for (SftpClient.DirEntry entry : listEntries(session, path)) {
            String name = entry.getFilename();
            if (!".".equals(name) && !"..".equals(name) && isDirectory(entry)) {
                names.add(name);
            }
        }
        return names;
    }

    // list() fails on a folder that does not exist, so check first and treat it as an empty folder
    private SftpClient.DirEntry[] listEntries(Session<SftpClient.DirEntry> session, String path) throws IOException {
        if (!session.exists(path)) {
            return new SftpClient.DirEntry[0];
        }
        SftpClient.DirEntry[] entries = session.list(path);
        return entries != null ? entries : new SftpClient.DirEntry[0];
    }

    // Symlinks are not followed: only real folders and files count
    private static boolean isDirectory(SftpClient.DirEntry entry) {
        SftpClient.Attributes attributes = entry.getAttributes();
        return attributes != null && attributes.isDirectory() && !attributes.isSymbolicLink();
    }

    private static boolean isRegularFile(SftpClient.DirEntry entry) {
        SftpClient.Attributes attributes = entry.getAttributes();
        return attributes != null && attributes.isRegularFile() && !attributes.isSymbolicLink();
    }

    // A value from the "meta" block of MPackage.json, or null
    private static String metaValue(JsonNode mappingPackage, String field) {
        JsonNode value = mappingPackage.path("meta").path(field);
        return value.isString() ? value.asString() : null;
    }

    // The number in a version folder name: "v3" -> 3. Other names (and absurdly long numbers) sort last.
    private static long versionNumber(String version) {
        return version.matches("[vV]\\d{1,9}") ? Long.parseLong(version.substring(1)) : -1;
    }

    // "/Packages/" and "/Packages" give the same root, so paths never get a double slash
    private static String normalizeRoot(String root) {
        String trimmed = root.trim();
        while (trimmed.length() > 1 && trimmed.endsWith("/")) {
            trimmed = trimmed.substring(0, trimmed.length() - 1);
        }
        return "/".equals(trimmed) ? "" : trimmed;
    }

    // The value becomes a folder name on SFTP, so it may not contain path or control characters
    private static String requireSafeSegment(String name, String value) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(name + " must not be empty");
        }
        String trimmed = value.trim();
        if (trimmed.contains("/") || trimmed.contains("\\") || trimmed.contains("..")
                || trimmed.startsWith(".") || trimmed.chars().anyMatch(Character::isISOControl)) {
            throw new IllegalArgumentException(name + " contains illegal characters");
        }
        return trimmed;
    }
}
