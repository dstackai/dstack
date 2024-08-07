export const prepareBackendConfigForApi = (backendConfig: TBackendConfig): TBackendConfig => {
    if (backendConfig.type !== 'aws' || !backendConfig.vpc_name) return backendConfig;

    return {
        ...backendConfig,
        vpc_name: backendConfig.vpc_name.trim(),
    };
};
