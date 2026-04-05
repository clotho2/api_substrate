/**
 * API QUEUE - Sequential API Call Management
 * 
 * Prevents parallel API calls for Tasks and Heartbeats to avoid:
 * - Multiple simultaneous requests causing timeouts
 * - 7x billing issues
 * - Resource contention
 * 
 * User Messages can still run in parallel (Discord events are independent)
 */

type QueuedOperation<T = any> = () => Promise<T>;

class APIQueue {
  private queue: Array<{ operation: QueuedOperation<any>; resolve: (value: any) => void; reject: (error: any) => void }> = [];
  private processing = false;
  private currentOperation: string | null = null;

  /**
   * Add operation to queue (Tasks and Heartbeats)
   * Returns promise that resolves when operation completes
   */
  async enqueue<T>(operation: QueuedOperation<T>, operationName: string): Promise<T> {
    return new Promise<T>((resolve, reject) => {
      this.queue.push({ operation, resolve, reject });
      console.log(`📋 [API Queue] Enqueued: ${operationName} (${this.queue.length} total in queue)`);
      
      // Start processing if not already running
      if (!this.processing) {
        this.processQueue();
      }
    });
  }

  /**
   * Process queue sequentially (one at a time)
   */
  private async processQueue(): Promise<void> {
    if (this.processing) {
      return; // Already processing
    }

    this.processing = true;

    while (this.queue.length > 0) {
      const item = this.queue.shift();
      if (item) {
        try {
          this.currentOperation = 'Processing...';
          const result = await item.operation();
          this.currentOperation = null;
          item.resolve(result);
        } catch (error) {
          this.currentOperation = null;
          console.error(`📋 [API Queue] Error processing operation:`, error);
          item.reject(error);
          // Continue with next operation even if this one failed
        }
      }
    }

    this.processing = false;
    console.log(`📋 [API Queue] Queue empty, waiting for new operations`);
  }

  /**
   * Get current queue status
   */
  getStatus(): { queueLength: number; processing: boolean; currentOperation: string | null } {
    return {
      queueLength: this.queue.length,
      processing: this.processing,
      currentOperation: this.currentOperation
    };
  }
}

// Singleton instance
export const apiQueue = new APIQueue();

