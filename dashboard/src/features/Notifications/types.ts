export type NotificationType = 'success';

export interface Notification {
    uid: string;
    title?: string;
    message: string;
    type: NotificationType;
}
