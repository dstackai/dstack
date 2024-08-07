export interface FormValues {
    instructions?: string;
    message: string;
}

export type Role = 'system' | 'user' | 'assistant' | 'tool';

export interface Message {
    role: Role;
    content: string;
}
