package be.essers.services.versioncontrol.service;

import be.essers.services.versioncontrol.domain.dto.MappingPackageOverviewDto;
import be.essers.services.versioncontrol.domain.dto.PackageVersionDto;

import java.util.List;

public interface PackageStorageService {

    List<MappingPackageOverviewDto> listPackages(String company);

    MappingPackageOverviewDto setActivePackage(String company, String packageType, String version, String user);

    List<PackageVersionDto> listVersions(String company, String packageType);
}
