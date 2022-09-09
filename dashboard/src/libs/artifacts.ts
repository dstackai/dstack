export const isJobArtifactParams = (params: { [key: string]: any }): params is IJobArtifactsFetchParams => {
    return typeof params.job_id === 'string';
};

export const artifactPathGetFolderName = (path: TArtifactPath): string => {
    return path.split('/')[3] ?? '';
};

export const artifactPathsToString = (paths: IJob['artifact_paths']): string => {
    if (paths === null || !paths.length) return '';

    return `${artifactPathGetFolderName(paths[0])}${paths.length > 1 ? `,…+${paths.length - 1}` : ''}`;
};

// TODO add test
export const artifactsToArtifactPaths = (artifacts: IArtifact[]): TArtifactPaths => {
    return artifacts.map((a) => a.artifact_path);
};
