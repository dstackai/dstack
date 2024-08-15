declare type TUserRole = 'user' | 'admin';
declare type TUserPermission =
    | 'DSTACK_USER_CAN_CREATE_PROJECTS'
    | 'DSTACK_USER_CAN_CREATE_GATEWAYS'
    | 'DSTACK_USER_CAN_CREATE_ON_PREM_FLEETS'

declare interface IUser {
    id: string,
    username: string;
    global_role: TUserRole
    email: string | null,
    permissions: TUserPermission[],
}

declare interface IUserWithCreds extends IUser {
    "creds": {
        "token": string
    }
}

declare interface IUserAuthData extends Pick<IUserWithCreds['creds'], 'token'>{}

declare interface IUserBillingInfo {
    balance: number
    is_payment_method_attached: boolean,
    default_payment_amount: number,
    billing_history: IPayment[]
}
