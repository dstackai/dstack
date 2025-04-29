declare type TVolumesListRequestParams = {
    project_name?: string;
    only_active?: boolean;
    prev_created_at?: string;
    prev_id?: string;
    limit?: number;
    ascending?: boolean;
}

declare interface IVolumeConfiguration {
    type: "volume",
    name?: string,
    backend: TBackendType,
    region: string,
    size?: number,
    volume_id?: string
}

declare interface IVolumeProvisioningData {
    backend?: TBackendType,
    volume_id: string,
    size_gb: number,
    availability_zone?: string
    price?:number
    attachable: boolean
    detachable: boolean
    backend_data?: string
}

declare interface IVolume {
    id: string
    name: string
    project_name: string,
    external: boolean,
    created_at: string,
    last_processed_at: string,
    status: "submitted" | "provisioning" | "active" | "failed"
    status_message?: string
    deleted: boolean
    deleted_at?: string
    volume_id?: string;
    configuration: IVolumeConfiguration,
    provisioning_data: IVolumeProvisioningData
    cost: number
    attachment_data: {
        device_name?: string
    }
}
