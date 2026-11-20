package be.essers.services.versioncontrol.service;

import java.util.List;

import be.essers.services.versioncontrol.domain.dto.MappingPackageOverviewDto;

public interface PackageStorageService {
    List<MappingPackageOverviewDto> listPackages(String company);
}
