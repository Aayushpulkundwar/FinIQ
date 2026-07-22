import { useDebugStore } from '../store/useDebugStore';

let isInitialized = false;

function truncateDetails(details: any): any {
  if (details === undefined || details === null) return details;
  
  let detailsStr = '';
  try {
    detailsStr = typeof details === 'object' ? JSON.stringify(details) : String(details);
  } catch {
    detailsStr = String(details);
  }

  if (detailsStr.length > 2000) {
    return detailsStr.substring(0, 2000) + '...truncated';
  }
  return details;
}

export function initDebugLogger() {
  if (!import.meta.env.DEV) return;
  if (isInitialized) return;
  isInitialized = true;

  const originalLog = console.log;
  const originalWarn = console.warn;
  const originalError = console.error;

  console.log = (...args: any[]) => {
    originalLog.apply(console, args);
    const message = args.map(arg => typeof arg === 'object' ? JSON.stringify(arg) : String(arg)).join(' ');
    useDebugStore.getState().addLog({
      level: 'info',
      source: 'console',
      message: message,
      details: args.length > 1 ? truncateDetails(args) : undefined,
    });
  };

  console.warn = (...args: any[]) => {
    originalWarn.apply(console, args);
    const message = args.map(arg => typeof arg === 'object' ? JSON.stringify(arg) : String(arg)).join(' ');
    useDebugStore.getState().addLog({
      level: 'warn',
      source: 'console',
      message: message,
      details: args.length > 1 ? truncateDetails(args) : undefined,
    });
  };

  console.error = (...args: any[]) => {
    originalError.apply(console, args);
    const message = args.map(arg => typeof arg === 'object' ? JSON.stringify(arg) : String(arg)).join(' ');
    useDebugStore.getState().addLog({
      level: 'error',
      source: 'console',
      message: message,
      details: args.length > 1 ? truncateDetails(args) : undefined,
    });
  };
}

export function logNetwork(
  method: string,
  url: string,
  status: number,
  durationMs: number,
  error?: any
) {
  if (!import.meta.env.DEV) return;

  const isSuccess = status >= 200 && status < 300;
  const level = isSuccess ? 'network' : 'error';
  const message = `${method} ${url} - ${status} (${durationMs}ms)`;
  
  useDebugStore.getState().addLog({
    level,
    source: 'network',
    message,
    details: truncateDetails({
      method,
      url,
      status,
      durationMs,
      error,
    }),
  });
}
