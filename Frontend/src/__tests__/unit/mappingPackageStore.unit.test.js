import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useMappingPackageStore } from '../../stores/mappingPackageStore'
import { fetchPackages, fetchPackageVersions, setActivePackage } from '../../services/mappingPackageOverviewService'

vi.mock('../../services/mappingPackageOverviewService')

const PACKAGES = [
    { company: 'brevalis', latestVersion: 'v1', createdAt: '2025-07-15T12:00:00Z', createdBy: 'analist_b', customerName: 'Brevalis', packageType: 'outbound' },
    { company: 'nouryon', latestVersion: 'v2', createdAt: '2026-11-12T10:00:00Z', createdBy: 'analist_a', customerName: 'Nouryon', packageType: 'inbound' },
    { company: 'nouryon', latestVersion: 'v1', createdAt: '2026-10-02T10:00:00Z', createdBy: 'analist_a', customerName: 'Nouryon', packageType: 'outbound' },
]

const VERSIONS = [
    { version: 'v3', createdAt: '2026-11-12T10:00:00Z', createdBy: 'analist_a', description: '2 mappings gewijzigd', isActive: false },
    { version: 'v2', createdAt: '2026-10-02T10:00:00Z', createdBy: 'analist_b', description: '1 mapping toegevoegd', isActive: true },
    { version: 'v1', createdAt: '2026-09-29T09:30:00Z', createdBy: 'analist_a', description: 'Eerste versie', isActive: false },
]

describe('mappingPackageStore', () => {
    beforeEach(() => {
        useMappingPackageStore.setState({ packages: null, loading: false, error: null })
        vi.clearAllMocks()
    })

    it('fetchPackages stores the list', async () => {
        // Arrange
        fetchPackages.mockResolvedValue(PACKAGES)

        // Act
        await useMappingPackageStore.getState().fetchPackages()

        // Assert
        const state = useMappingPackageStore.getState()
        expect(state.packages).toEqual(PACKAGES)
        expect(state.loading).toBe(false)
        expect(state.error).toBeNull()
    })

    it('fetches all packages when no company is given', async () => {
        // Arrange
        fetchPackages.mockResolvedValue(PACKAGES)

        // Act
        await useMappingPackageStore.getState().fetchPackages()

        // Assert
        expect(fetchPackages).toHaveBeenCalledTimes(1)
        expect(fetchPackages).toHaveBeenCalledWith(undefined)
    })

    it('fetches only the packages of the given company', async () => {
        // Arrange
        const nouryon = PACKAGES.filter((p) => p.company === 'nouryon')
        fetchPackages.mockResolvedValue(nouryon)

        // Act
        await useMappingPackageStore.getState().fetchPackages('nouryon')

        // Assert
        expect(fetchPackages).toHaveBeenCalledWith('nouryon')
        expect(useMappingPackageStore.getState().packages).toEqual(nouryon)
    })

    it('keeps a company once per package type', async () => {
        // Arrange
        fetchPackages.mockResolvedValue(PACKAGES)

        // Act
        await useMappingPackageStore.getState().fetchPackages()

        // Assert
        const types = useMappingPackageStore.getState().packages
            .filter((p) => p.company === 'nouryon')
            .map((p) => p.packageType)
        expect(types).toEqual(['inbound', 'outbound'])
    })

    it('stores an empty list when there are no packages', async () => {
        // Arrange
        fetchPackages.mockResolvedValue([])

        // Act
        await useMappingPackageStore.getState().fetchPackages()

        // Assert
        const state = useMappingPackageStore.getState()
        expect(state.packages).toEqual([])
        expect(state.error).toBeNull()
    })

    it('sets loading while fetching', async () => {
        // Arrange
        fetchPackages.mockResolvedValue(PACKAGES)

        // Act
        const promise = useMappingPackageStore.getState().fetchPackages()

        // Assert
        const state = useMappingPackageStore.getState()
        expect(state.loading).toBe(true)

        await promise
    })

    it('clears the previous error when fetching again', async () => {
        // Arrange
        useMappingPackageStore.setState({ error: 'down' })
        fetchPackages.mockResolvedValue(PACKAGES)

        // Act
        const promise = useMappingPackageStore.getState().fetchPackages()

        // Assert
        expect(useMappingPackageStore.getState().error).toBeNull()

        await promise
    })

    it('stores the error when fetching fails', async () => {
        // Arrange
        fetchPackages.mockRejectedValue(new Error('Loading mapping packages failed (HTTP 502)'))

        // Act
        await useMappingPackageStore.getState().fetchPackages()

        // Assert
        const state = useMappingPackageStore.getState()
        expect(state.packages).toBeNull()
        expect(state.loading).toBe(false)
        expect(state.error).toBe('Loading mapping packages failed (HTTP 502)')
    })

    it('clears the list that was shown when fetching fails', async () => {
        // Arrange
        useMappingPackageStore.setState({ packages: PACKAGES })
        fetchPackages.mockRejectedValue(new Error('down'))

        // Act
        await useMappingPackageStore.getState().fetchPackages()

        // Assert
        const state = useMappingPackageStore.getState()
        expect(state.packages).toBeNull()
        expect(state.error).toBe('down')
    })

    it('shows a general error when the failure is not an Error', async () => {
        // Arrange
        fetchPackages.mockRejectedValue('broken')

        // Act
        await useMappingPackageStore.getState().fetchPackages()

        // Assert
        const state = useMappingPackageStore.getState()
        expect(state.error).toBe('Onbekende fout')
        expect(state.loading).toBe(false)
    })

    //---

    it('fetchVersions stores the versions', async () => {
        // Arrange
        fetchPackageVersions.mockResolvedValue(VERSIONS)

        // Act
        await useMappingPackageStore.getState().fetchVersions('brevalis', 'inbound')

        // Assert
        const state = useMappingPackageStore.getState()
        expect(fetchPackageVersions).toHaveBeenCalledWith('brevalis', 'inbound')
        expect(state.versions).toEqual(VERSIONS)
        expect(state.versionsLoading).toBe(false)
        expect(state.versionsError).toBeNull()
    })

    it('sets versionsLoading while fetching', async () => {
        // Arrange
        fetchPackageVersions.mockResolvedValue(VERSIONS)

        // Act
        const promise = useMappingPackageStore.getState().fetchVersions('brevalis', 'inbound')

        // Assert
        const state = useMappingPackageStore.getState()
        expect(state.versionsLoading).toBe(true)

        await promise
    })

    it('clears the previous versionsError when fetching again', async () => {
        // Arrange
        useMappingPackageStore.setState({ versionsError: 'down' })
        fetchPackageVersions.mockResolvedValue(VERSIONS)

        // Act
        const promise = useMappingPackageStore.getState().fetchVersions('brevalis', 'inbound')

        // Assert
        expect(useMappingPackageStore.getState().versionsError).toBeNull()

        await promise
    })

    it('stores the versionsError when fetching fails', async () => {
        // Arrange
        fetchPackageVersions.mockRejectedValue(new Error('Loading versions failed (HTTP 502)'))

        // Act
        await useMappingPackageStore.getState().fetchVersions('brevalis', 'inbound')

        // Assert
        const state = useMappingPackageStore.getState()
        expect(state.versions).toBeNull()
        expect(state.versionsLoading).toBe(false)
        expect(state.versionsError).toBe('Loading versions failed (HTTP 502)')
    })

    it('clears the version list that was shown when fetching fails', async () => {
        // Arrange
        useMappingPackageStore.setState({ versions: VERSIONS })
        fetchPackageVersions.mockRejectedValue(new Error('down'))

        // Act
        await useMappingPackageStore.getState().fetchVersions('brevalis', 'inbound')

        // Assert
        const state = useMappingPackageStore.getState()
        expect(state.versions).toBeNull()
        expect(state.versionsError).toBe('down')
    })

    it('shows a general versionsError when the failure is not an Error', async () => {
        // Arrange
        fetchPackageVersions.mockRejectedValue('broken')

        // Act
        await useMappingPackageStore.getState().fetchVersions('brevalis', 'inbound')

        // Assert
        const state = useMappingPackageStore.getState()
        expect(state.versionsError).toBe('Onbekende fout')
        expect(state.versionsLoading).toBe(false)
    })

    it('does not touch the overview when fetching versions fails', async () => {
        // Arrange
        useMappingPackageStore.setState({ packages: PACKAGES, loading: false, error: null })
        fetchPackageVersions.mockRejectedValue(new Error('down'))

        // Act
        await useMappingPackageStore.getState().fetchVersions('brevalis', 'inbound')

        // Assert
        const state = useMappingPackageStore.getState()
        expect(state.packages).toEqual(PACKAGES)
        expect(state.error).toBeNull()
    })

    //----

    it('setActivePackage calls service and updates active package in memory', async () => {
        // Arrange
        useMappingPackageStore.setState({ packages: [...PACKAGES] })
        const updatedPackage = {
            ...PACKAGES[1],
            activeVersion: 'v1',
            activeUpdatedAt: '2026-11-20T22:00:00Z',
            activeUpdatedBy: 'analist_test',
        }
        setActivePackage.mockResolvedValue(updatedPackage)

        // Act
        await useMappingPackageStore.getState().setActivePackage('nouryon', 'inbound', 'v1', 'analist_test')

        // Assert
        expect(setActivePackage).toHaveBeenCalledWith('nouryon', 'inbound', 'v1', 'analist_test')
        const state = useMappingPackageStore.getState()
        const updated = state.packages.find((p) => p.company === 'nouryon' && p.packageType === 'inbound')
        expect(updated.activeVersion).toBe('v1')
        expect(updated.activeUpdatedBy).toBe('analist_test')
    })
})
