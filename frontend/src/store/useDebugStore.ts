import { create } from 'zustand';

export interface DebugLogEntry {
  id: string;
  timestamp: Date;
  level: 'info' | 'warn' | 'error' | 'network';
  source: string;
  message: string;
  details?: any;
}

interface DebugState {
  logs: DebugLogEntry[];
  isOpen: boolean;
  addLog: (entry: Omit<DebugLogEntry, 'id' | 'timestamp'> & { timestamp?: Date }) => void;
  clearLogs: () => void;
  toggleOpen: () => void;
}

export const useDebugStore = create<DebugState>((set) => ({
  logs: [],
  isOpen: false,
  addLog: (entry) => set((state) => {
    const newEntry: DebugLogEntry = {
      id: Math.random().toString(36).substring(7),
      timestamp: entry.timestamp || new Date(),
      level: entry.level,
      source: entry.source,
      message: entry.message,
      details: entry.details,
    };
    const updatedLogs = [...state.logs, newEntry];
    if (updatedLogs.length > 500) {
      updatedLogs.shift(); // Drop oldest log
    }
    return { logs: updatedLogs };
  }),
  clearLogs: () => set({ logs: [] }),
  toggleOpen: () => set((state) => ({ isOpen: !state.isOpen })),
}));
