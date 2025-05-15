import { Observable, Subject } from 'rxjs';

export function streamTextGenerationObservable(
    sessionId: string,
    prompt: string,
    toolsConfig: Record<string, any[]>,    llmConfigId?: string | null,
    baseUrl?: string, // Optional base URL override
    // The socketIoUrl and socketIoPath parameters are kept for backward compatibility but no longer used
    debugMode: boolean = false // Add debug mode parameter with default false
): Observable<string> {
    // Create a new Subject that will emit text tokens as they come in
    const subject = new Subject<string>();
} 