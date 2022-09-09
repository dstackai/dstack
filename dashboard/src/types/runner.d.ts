declare interface IRunnerGpu {
  name: string;
  memory_mib: null| number;
}

declare interface IRunnerResources {
  cpu: {
    count: null | number;
  },
  memory_mib: number;
  gpus: IRunnerGpu[]
  interruptible?: boolean | null;
}

declare interface IRunner {
  runner_id: string;
  user_name: string;
  runner_name: string;
  host_name: string;
  status: 'live' | 'requested';
  updated_at: number;
  resources: IRunnerResources;
  region_name?: null | string,
  estimated_price: null | number;
  purchase_type: null | 'on-demand' | 'spot';
}
