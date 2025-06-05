export interface FormValues {
    instructions?: string;
    message: string;
}

export type Role = 'system' | 'user' | 'assistant' | 'tool';

export interface Message {
    role: Role;
    content: string;
    tool_call_id?: string; 
}

// Add new type for cancellation (only if you use CancelToken, not needed for AbortController)
declare module 'openai' {
    interface CompletionCreateParams {
        cancelToken?: any; // Replace 'any' with the actual CancelToken type if needed
    }
}
