declare type TMeteringGroupBy = 'day' | 'month' | 'project' | 'user';

declare type TMeteringListRequestParams = {
    start: string;
    end: string;
    group_by: TMeteringGroupBy[];
    model_project_name?: IProject['project_name'];
    model_name?: IModel['name'];
    project_name?: IProject['project_name'];
    user_name?: IUser['username'];
};

declare interface IMeteringRow {
    day?: string | null;
    // The first day of the month
    month?: string | null;
    project_name?: string | null;
    user_name?: string | null;
    input_tokens: number;
    cached_input_tokens: number;
    output_tokens: number;
}
