declare type TPresetsListRequestParams = {
    project_name?: string;
    username?: string;
    base?: string;
    prev_created_at?: string;
    prev_id?: string;
    limit?: number;
    ascending?: boolean;
};

declare interface IPresetBenchmark {
    tool: string;
    tool_version: string;
    command: string;
    workload: HashMap;
    metrics: HashMap;
}

declare interface IPresetVerificationReplicaGroup {
    name: string;
    replicas: HashMap[];
}

declare interface IPresetSpec {
    preset: {
        base: string;
        repo: string;
        context_length: number;
        service: HashMap;
        benchmark: IPresetBenchmark;
        verified_on: IPresetVerificationReplicaGroup[];
    };
    file_archives: { id: string; path: string }[];
}

declare interface IPreset {
    id: string;
    name: string | null;
    base: string;
    repo: string;
    created_at: string;
    pushed_by: string;
    project_name: string;
}

declare interface IPresetDetails extends IPreset {
    spec: IPresetSpec;
}

declare interface IPresetListResponse {
    presets: IPreset[];
}
