package be.essers.services.versioncontrol.domain.proposal.api.dto;

/**
 * One row of the proposal overview on Home.
 * {@code company} is the customer folder on SFTP (used in links),
 * {@code customerName} is the name the analist entered at the upload (shown in the list).
 */
public record CompanyProposalOverviewDto(
        String company,
        String latestVersion,
        String filename,
        String fullPath,
        String createdDate,
        String createdBy,
        String description,
        String status,
        String aiStatus,
        String customerName
) {
    public CompanyProposalOverviewDto(String company, String latestVersion, String filename, String fullPath,
                                      String createdDate, String createdBy, String description,
                                      String status, String aiStatus) {
        this(company, latestVersion, filename, fullPath, createdDate, createdBy, description, status, aiStatus, null);
    }
}
