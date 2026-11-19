export interface FormValues {
    message: string;
}

export type Role = 'system' | 'user' | 'assistant' | 'tool';

export interface Message {
    role: Role;
    content: string;
    // What a thinking model streamed before its answer. The chat shows it, and a request doesn't send it back
    thinking?: string;
    // Why the reply's stream ended: `length` when the reply was cut at the limit of tokens
    finish_reason?: string | null;
}
