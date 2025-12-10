declare type TEventTargetType = 'project' | 'user' | 'fleet' | 'instance' | 'run' | 'job';

declare type TEventListRequestParams = Omit<TBaseRequestListParams, 'prev_created_at'> & {
    prev_recorded_at?: string;
    target_projects?: string[];
    target_users?: string[];
    target_fleets?: string[];
    target_instances?: string[];
    target_runs?: string[];
    target_jobs?: string[];
    within_projects?: string[];
    within_fleets?: string[];
    within_runs?: string[];
    include_target_types?: TEventTargetType[];
    actors?: string[];
};

declare interface IEventTarget {
    type: 'project' | 'user' | 'fleet' | 'instance' | 'run' | 'job';
    project_id?: string;
    project_name?: string;
    id: string;
    name: string;
}

declare interface IEvent {
    id: string;
    recorded_at: string;
    message: string;
    actor_user_id: string | null;
    actor_user: string | null;
    targets: IEventTarget[];
}
