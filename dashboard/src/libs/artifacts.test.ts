import { artifactPathGetFolderName, artifactPathsToString } from './artifacts';

describe('Test Artifacts libs', () => {
    test('Job Artifact path get folder name', () => {
        expect(artifactPathGetFolderName('')).toBe('');
        expect(artifactPathGetFolderName('olgenn/tame-dodo-1/707b5f38ca86')).toBe('');
        expect(artifactPathGetFolderName('olgenn/tame-dodo-1/707b5f38ca86/models')).toBe('models');
        expect(artifactPathGetFolderName('olgenn/tame-dodo-1/14663b44d3a3/checkpoint')).toBe('checkpoint');
    });

    test('Job Artifact paths to Strig', () => {
        expect(artifactPathsToString(null)).toBe('');
        expect(artifactPathsToString([])).toBe('');
        expect(artifactPathsToString(['olgenn/tame-dodo-1/707b5f38ca86/models'])).toBe('models');

        expect(
            artifactPathsToString(['olgenn/tame-dodo-1/14663b44d3a3/checkpoint', 'olgenn/tame-dodo-1/14663b44d3a3/samples']),
        ).toBe('checkpoint,…+1');
    });
});
