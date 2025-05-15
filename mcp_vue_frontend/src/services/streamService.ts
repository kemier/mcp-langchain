import { Observable, Subject } from 'rxjs';

// Define event types for better type safety
export enum StreamEventType {
  TOKEN = 'token',
  ERROR = 'error_event',
  INFO = 'info',
  FINAL = 'final',
  ON_CHAIN_END = 'on_chain_end',
  END = 'end'
}

export interface StreamEvent {
  type: StreamEventType | string;
  data: any;
}

/**
 * Stream client service that handles WebSocket connections
 * with robust error handling and reconnection logic
 */
export class StreamService {
  private static instance: StreamService;
  private activeConnections: Map<string, { 
    socket: WebSocket, 
    reconnectAttempts: number 
  }> = new Map();
  private maxReconnectAttempts = 3;
  private reconnectDelay = 1000; // Start with 1 second

  private constructor() {}

  public static getInstance(): StreamService {
    if (!StreamService.instance) {
      StreamService.instance = new StreamService();
    }
    return StreamService.instance;
  }

  /**
   * Creates a stream that will use the appropriate technology based on the provided URL
   * If the URL starts with 'ws:' or 'wss:', WebSocket will be used
   */
  public createStream(url: string, payload: any, sessionId: string, debugMode = false): Observable<StreamEvent> {
    // Check if the URL is already a WebSocket URL
    if (url.startsWith('ws:') || url.startsWith('wss:')) {
      return this.createWebSocketStream(url, payload, sessionId, debugMode);
    } else {
      // Convert HTTP URLs to WebSocket URLs
      const wsUrl = url.replace(/^http/, 'ws') + '/ws/chat';
      return this.createWebSocketStream(wsUrl, payload, sessionId, debugMode);
    }
  }

  /**
   * Create a WebSocket-based stream
   * @param url The WebSocket URL
   * @param payload The data to send
   * @param sessionId Session identifier
   * @param debugMode Enable debug logging
   * @returns Observable of stream events
   */
  public createWebSocketStream(url: string, payload: any, sessionId: string, debugMode = false): Observable<StreamEvent> {
    if (debugMode) console.log(`[STREAM-SERVICE] Creating WebSocket stream to ${url} for session: ${sessionId}`);
    
    return new Observable<StreamEvent>(observer => {
      try {
        // Create WebSocket connection
        const socket = new WebSocket(url);
        
        // Store the connection for potential reconnect/cleanup
        this.activeConnections.set(sessionId, { 
          socket, 
          reconnectAttempts: 0 
        });
        
        // Set a connection timeout
        const connectionTimeoutId = setTimeout(() => {
          if (debugMode) console.log('[STREAM-TRACE] ⚠️ CONNECTION TIMEOUT TRIGGERED');
          socket.close();
          observer.error(new Error('Connection timeout after 60 seconds'));
        }, 60000);
        
        // Handle WebSocket events
        socket.onopen = (event) => {
          if (debugMode) console.log(`[STREAM-SERVICE] WebSocket connected for session: ${sessionId}`);
          
          // Clear connection timeout
          clearTimeout(connectionTimeoutId);
          
          // Send the payload as a JSON string
          const messageStr = JSON.stringify(payload);
          if (debugMode) console.log(`[STREAM-SERVICE] Sending payload: ${messageStr.substring(0, 100)}...`);
          
          // 添加会话ID到payload
          const enhancedPayload = {
            ...payload,
            session_id: sessionId 
          };
          
          // Add explicit delay before sending to ensure the connection is fully established
          setTimeout(() => {
            if (socket.readyState === WebSocket.OPEN) {
              socket.send(JSON.stringify(enhancedPayload));
              if (debugMode) console.log(`[STREAM-SERVICE] Payload sent successfully with session_id: ${sessionId}`);
            } else {
              if (debugMode) console.error(`[STREAM-SERVICE] Cannot send payload, socket state: ${socket.readyState}`);
              observer.error(new Error(`WebSocket not in OPEN state (${socket.readyState})`));
            }
          }, 500); // 500ms delay
          
          // Notify that connection is established
          observer.next({
            type: 'info',
            data: 'WebSocket connection established'
          });
        };
        
        socket.onmessage = (event) => {
          if (debugMode) console.log(`[STREAM-SERVICE] Message received for session ${sessionId}`);
          
          try {
            // Parse the message as JSON
            const data = JSON.parse(event.data);
            if (debugMode) console.log(`[STREAM-SERVICE] Parsed message:`, data);
            
            // Process the message based on its type
            if (data.type && typeof data.type === 'string') {
              // Map to StreamEventType if possible
              let eventType = data.type;
              if (Object.values(StreamEventType).includes(data.type as StreamEventType)) {
                eventType = data.type as StreamEventType;
              }
              
              // Emit the event
              observer.next({
                type: eventType,
                data: data.data
              });
              
              // If this is the end event, complete the observer
              if (eventType === StreamEventType.END) {
                console.log(`[STREAM-SERVICE] Received END event for session ${sessionId}, completing stream`);
                observer.complete();
              }
            } else {
              // Handle message without type
              if (debugMode) console.warn(`[STREAM-SERVICE] Message has no type:`, data);
              observer.next({
                type: 'unknown',
                data
              });
            }
            
          } catch (e) {
            if (debugMode) console.error(`[STREAM-SERVICE] Error parsing message:`, e);
            // If we can't parse it as JSON, treat as plain text
            observer.next({
              type: 'token',
              data: event.data
            });
          }
        };
        
        socket.onerror = (error) => {
          if (debugMode) {
            console.error('[STREAM-TRACE] ❌ WebSocket error:', error);
            console.error('[STREAM-TRACE] WebSocket URL:', url);
            console.error('[STREAM-TRACE] WebSocket readyState:', socket.readyState);
          }
          
          // Notify about the error
          observer.next({
            type: 'error_event',
            data: {
              error: "WebSocket error occurred",
              recoverable: true,
              details: JSON.stringify(error)
            }
          });
        };
        
        socket.onclose = (event) => {
          if (debugMode) console.log(`[STREAM-TRACE] 🔌 WebSocket closed: Code: ${event.code}, Reason: ${event.reason || 'No reason provided'}`);
          
          // Check if we need to reconnect
          const connectionInfo = this.activeConnections.get(sessionId);
          
          if (connectionInfo && connectionInfo.reconnectAttempts < this.maxReconnectAttempts) {
            const nextAttempt = connectionInfo.reconnectAttempts + 1;
            if (debugMode) console.log(`[STREAM-TRACE] 🔄 Reconnecting... Attempt ${nextAttempt}/${this.maxReconnectAttempts}`);
            
            // Update reconnect attempts
            this.activeConnections.set(sessionId, {
              ...connectionInfo,
              reconnectAttempts: nextAttempt
            });
            
            // Notify about reconnection
            observer.next({
              type: 'info',
              data: `WebSocket disconnected. Reconnecting (${nextAttempt}/${this.maxReconnectAttempts})...`
            });
            
            // Exponential backoff for reconnection
            const delayMs = Math.min(this.reconnectDelay * Math.pow(2, nextAttempt - 1), 30000);
            
            // Try reconnecting
            const reconnectTimeoutId = setTimeout(() => {
              // Create new WebSocket stream and pipe events to current observer
              const newStream = this.createWebSocketStream(url, payload, sessionId, debugMode);
              const subscription = newStream.subscribe({
                next: (event) => observer.next(event),
                error: (err) => observer.error(err),
                complete: () => observer.complete()
              });
              
              // Clean up the subscription when this observable is unsubscribed
              return () => subscription.unsubscribe();
            }, delayMs);
            
            // Return cleanup function that clears the timeout
            return () => clearTimeout(reconnectTimeoutId);
          } else {
            // Max reconnect attempts reached or no connection info
            if (debugMode) {
              console.log(`[STREAM-TRACE] ⛔ Not reconnecting. ${
                !connectionInfo 
                  ? 'Connection info not found.' 
                  : `Max reconnect attempts (${this.maxReconnectAttempts}) reached.`
              }`);
            }
            
            // Remove from active connections
            this.activeConnections.delete(sessionId);
            
            // Complete the observable
            observer.complete();
          }
        };
        
        // Return cleanup function
        return () => {
          clearTimeout(connectionTimeoutId);
          if (socket && socket.readyState === WebSocket.OPEN) {
            socket.close();
          }
          this.activeConnections.delete(sessionId);
        };
      } catch (error) {
        console.error('[STREAM-SERVICE] Error creating WebSocket stream:', error);
        observer.error(error);
        return () => {}; // Return empty cleanup function
      }
    });
  }

  /**
   * Closes an active connection
   */
  public closeStream(sessionId: string): void {
    const connection = this.activeConnections.get(sessionId);
    if (connection) {
      connection.socket.close();
      this.activeConnections.delete(sessionId);
      console.log(`[STREAM-TRACE] 🛑 Closed connection for session: ${sessionId}`);
    }
  }

  /**
   * Closes all active connections
   */
  public closeAllStreams(): void {
    for (const [sessionId, connection] of this.activeConnections.entries()) {
      connection.socket.close();
      console.log(`[STREAM-TRACE] 🛑 Closed connection for session: ${sessionId}`);
    }
    this.activeConnections.clear();
  }
}

// Export singleton instance
export const streamService = StreamService.getInstance(); 