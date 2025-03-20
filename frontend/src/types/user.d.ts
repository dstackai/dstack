declare type TUserRole = 'user' | 'admin';
declare type TUserPermission = 'CAN_CREATE_PROJECTS';
declare type TUserPermissionKeys = 'can_create_projects';

declare interface IUserResponseData {
    id: string;
    username: string;
    global_role: TUserRole;
    email: string | null;
    permissions: Record<TUserPermissionKeys, boolean>;
}

declare interface IUser {
    id: string;
    username: string;
    global_role: TUserRole;
    email: string | null;
    permissions: TUserPermission[];
    created_at: string;
    active: boolean;
}

declare interface IUserWithCreds extends IUser {
    creds: {
        token: string;
    };
}

declare interface IUserAuthData extends Pick<IUserWithCreds['creds'], 'token'> {}

declare interface IUserBillingInfo {
    balance: number;
    is_payment_method_attached: boolean;
    default_payment_amount: number;
    billing_history: IPayment[];
}
