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
          if (debugMode) {
            console.log('[STREAM-TRACE] ⚠️ CONNECTION TIMEOUT TRIGGERED');
            console.log(`[STREAM-TRACE] Socket readyState at timeout: ${socket.readyState}`);
          }
          socket.close();
          observer.error(new Error('Connection timeout after 60 seconds'));
        }, 60000);
        
        // Handle WebSocket events
        socket.onopen = (event) => {
          if (debugMode) console.log(`[STREAM-SERVICE][${sessionId}] WebSocket connected.`);
          
          // Clear connection timeout
          clearTimeout(connectionTimeoutId);
          
          // Send the payload as a JSON string
          const enhancedPayload = {
            ...payload,
            session_id: sessionId 
          };
          const finalMessageStr = JSON.stringify(enhancedPayload);
          if (debugMode) console.log(`[STREAM-SERVICE][${sessionId}] Sending final payload: ${finalMessageStr}`);
          
          // Add explicit delay before sending to ensure the connection is fully established
          setTimeout(() => {
            if (socket.readyState === WebSocket.OPEN) {
              socket.send(finalMessageStr);
              if (debugMode) console.log(`[STREAM-SERVICE][${sessionId}] Payload sent successfully.`);
            } else {
              if (debugMode) console.error(`[STREAM-SERVICE][${sessionId}] Cannot send payload, socket state: ${socket.readyState}`);
              observer.error(new Error(`WebSocket not in OPEN state (${socket.readyState}) for session ${sessionId}`));
            }
          }, 500); // 500ms delay
          
          // Notify that connection is established
          observer.next({
            type: 'info',
            data: 'WebSocket connection established'
          });
        };
        
        socket.onmessage = (event) => {
          // Log the raw event data FIRST
          if (debugMode) {
            console.log(`[STREAM-SERVICE-RAW][${sessionId}] Raw WebSocket message received:`, event.data);
          }
          
          try {
            // Parse the message as JSON
            const data = JSON.parse(event.data);
            if (debugMode) console.log(`[STREAM-SERVICE][${sessionId}] Parsed message content:`, JSON.stringify(data, null, 2));
            
            // Process the message based on its type
            if (data.type && typeof data.type === 'string') {
              // Map to StreamEventType if possible
              let eventType = data.type;
              if (Object.values(StreamEventType).includes(data.type as StreamEventType)) {
                eventType = data.type as StreamEventType;
              }
              if (debugMode) console.log(`[STREAM-SERVICE][${sessionId}] Determined eventType: '${eventType}', data to emit:`, JSON.stringify(data.data, null, 2));
              
              // Emit the event
              observer.next({
                type: eventType,
                data: data.data
              });
              
              // If this is the end event, complete the observer
              if (eventType === StreamEventType.END) {
                if (debugMode) console.log(`[STREAM-SERVICE][${sessionId}] Received END event, completing stream.`);
                observer.complete();
              }
            } else {
              // Handle message without type
              if (debugMode) console.warn(`[STREAM-SERVICE][${sessionId}] Message has no type:`, data);
              observer.next({
                type: 'unknown',
                data
              });
            }
            
          } catch (e) {
            if (debugMode) console.error(`[STREAM-SERVICE][${sessionId}] Error parsing message or unknown message structure. Raw data:`, event.data, 'Error:', e);
            // If we can't parse it as JSON, treat as plain text
            observer.next({
              type: 'token', // Or a generic 'raw_data' type
              data: event.data
            });
          }
        };
        
        socket.onerror = (error) => {
          if (debugMode) {
            console.error(`[STREAM-TRACE][${sessionId}] ❌ WebSocket error:`, error);
            console.error(`[STREAM-TRACE][${sessionId}] WebSocket URL:`, url);
            console.error(`[STREAM-TRACE][${sessionId}] WebSocket readyState:`, socket.readyState);
          }
          
          // Notify about the error
          observer.next({
            type: 'error_event',
            data: {
              error: "WebSocket error occurred",
              recoverable: true, // Assuming most ws errors might be recoverable with a new connection
              details: JSON.stringify(error) // Or a more structured error
            }
          });
          // Do not call observer.error() or observer.complete() here if reconnection is handled in onclose
        };
        
        socket.onclose = (event) => {
          if (debugMode) {
            console.log(`[STREAM-TRACE][${sessionId}] 🔌 WebSocket closed: Code: ${event.code}, Reason: ${event.reason || 'No reason provided'}, WasClean: ${event.wasClean}`);
            const connInfoForClose = this.activeConnections.get(sessionId);
            if (connInfoForClose) {
              console.log(`[STREAM-TRACE][${sessionId}] Connection info at close: ReconnectAttempts: ${connInfoForClose.reconnectAttempts}`);
            }
          }
          
          const connectionInfo = this.activeConnections.get(sessionId);

          if (event.wasClean) { // If the WebSocket was closed cleanly by the server
            if (debugMode) console.log(`[STREAM-SERVICE][${sessionId}] WebSocket closed cleanly. Completing stream.`);
            this.activeConnections.delete(sessionId);
            observer.complete(); // Complete the stream
          } else if (connectionInfo && connectionInfo.reconnectAttempts < this.maxReconnectAttempts) {
            // Unclean close, attempt to reconnect
            const nextAttempt = connectionInfo.reconnectAttempts + 1;
            if (debugMode) console.log(`[STREAM-TRACE][${sessionId}] 🔄 Reconnecting (unclean close)... Attempt ${nextAttempt}/${this.maxReconnectAttempts}`);
            
            this.activeConnections.set(sessionId, {
              ...connectionInfo,
              reconnectAttempts: nextAttempt
            });
            
            observer.next({
              type: 'info',
              data: `WebSocket disconnected. Reconnecting (${nextAttempt}/${this.maxReconnectAttempts})...`
            });
            
            const delayMs = Math.min(this.reconnectDelay * Math.pow(2, nextAttempt - 1), 30000);
            
            const reconnectTimeoutId = setTimeout(() => {
              const newStream = this.createWebSocketStream(url, payload, sessionId, debugMode); // payload might need to be the original one
              const subscription = newStream.subscribe({
                next: (newEvent) => observer.next(newEvent),
                error: (err) => observer.error(err), // If reconnect itself fails critically
                complete: () => observer.complete() // If reconnected stream completes
              });
              // It's tricky to manage cleanup of this inner subscription if outer one is unsubscribed.
              // This part of the logic might need more robust handling for chained subscriptions.
            }, delayMs);

            // How to handle unsubscription during reconnect delay?
            // The outer observable's cleanup (returned from new Observable()) will run if it's unsubscribed.
            // We should clear this timeout there.
            // For now, this logic is simplified. Consider a more robust RxJS operator for retry/repeat.

          } else {
            // Max reconnect attempts reached for unclean close, or no connection info
            if (debugMode) {
              console.log(`[STREAM-SERVICE][${sessionId}] Max reconnect attempts reached or no connection info for unclean close. Completing stream.`);
            }
            this.activeConnections.delete(sessionId);
            observer.complete(); // Complete the stream
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