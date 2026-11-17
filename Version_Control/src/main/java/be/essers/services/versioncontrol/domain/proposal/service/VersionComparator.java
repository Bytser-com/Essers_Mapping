package be.essers.services.versioncontrol.domain.proposal.service;

import java.util.Comparator;

/**
 * Compares version strings like "v1", "v2", "v3", "v10", "1.0.0", "v2.1"
 * so that "v10" is correctly considered greater than "v2".
 */
public class VersionComparator implements Comparator<String> {

    public static final VersionComparator INSTANCE = new VersionComparator();

    @Override
    public int compare(String v1, String v2) {
        if (v1 == null && v2 == null) {
            return 0;
        }
        if (v1 == null) {
            return -1;
        }
        if (v2 == null) {
            return 1;
        }

        String clean1 = v1.trim().replaceFirst("^[vV]", "");
        String clean2 = v2.trim().replaceFirst("^[vV]", "");

        String[] parts1 = clean1.split("[._-]");
        String[] parts2 = clean2.split("[._-]");

        int length = Math.max(parts1.length, parts2.length);
        for (int i = 0; i < length; i++) {
            String part1 = i < parts1.length ? parts1[i] : "0";
            String part2 = i < parts2.length ? parts2[i] : "0";

            boolean isNum1 = part1.matches("\\d+");
            boolean isNum2 = part2.matches("\\d+");

            if (isNum1 && isNum2) {
                try {
                    int num1 = Integer.parseInt(part1);
                    int num2 = Integer.parseInt(part2);
                    if (num1 != num2) {
                        return Integer.compare(num1, num2);
                    }
                } catch (NumberFormatException ignored) {
                    int comp = part1.compareTo(part2);
                    if (comp != 0) {
                        return comp;
                    }
                }
            } else {
                int comp = part1.compareToIgnoreCase(part2);
                if (comp != 0) {
                    return comp;
                }
            }
        }
        return 0;
    }
}
