"use client";

import { useEffect, useState, useCallback } from "react";
import { getWebSocketUrl, type Stats, type Portfolio, type Bot } from "./api";

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

  const connect = useCallback(() => {
    const ws = new WebSocket(getWebSocketUrl());

    ws.onopen = () => setConnected(true);
    ws.onclose = () => {
      setConnected(false);
      setTimeout(connect, 3000);
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

    return ws;
  }, []);

  useEffect(() => {
    const ws = connect();
    return () => ws.close();
  }, [connect]);

  return { stats, portfolios, bots, connected, lastUpdate };
}
