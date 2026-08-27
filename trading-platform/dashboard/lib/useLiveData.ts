"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { getWebSocketUrlAsync, type Stats, type Portfolio, type Bot } from "./api";

type LiveData = {
  stats: Stats | null;
  portfolios: Portfolio[];
  bots: Bot[];
  connected: boolean;
  lastUpdate: string | null;
};

export function useLiveData(): LiveData {
  const [stats, setStats] = useState<Stats | null>(null);
  const [portfolios, setPortfolios] = useState<Portfolio[]>([]);
  const [bots, setBots] = useState<Bot[]>([]);
  const [connected, setConnected] = useState(false);
  const [lastUpdate, setLastUpdate] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const connect = useCallback(async () => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    try {
      const url = await getWebSocketUrlAsync();
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => setConnected(true);
      ws.onclose = () => {
        setConnected(false);
        wsRef.current = null;
        reconnectTimer.current = setTimeout(() => {
          void connect();
        }, 3000);
      };
      ws.onerror = () => ws.close();
      ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.type === "update") {
          setStats(data.stats);
          setPortfolios(data.portfolios);
          setBots(data.bots);
          setLastUpdate(data.timestamp);
        }
      };
    } catch {
      setConnected(false);
      reconnectTimer.current = setTimeout(() => {
        void connect();
      }, 3000);
    }
  }, []);

  useEffect(() => {
    void connect();
    return () => {
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, [connect]);

  return { stats, portfolios, bots, connected, lastUpdate };
}
