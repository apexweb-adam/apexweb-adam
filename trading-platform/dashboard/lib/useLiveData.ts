"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import {
  fetchAPI,
  getWebSocketUrlAsync,
  type Stats,
  type Portfolio,
  type Bot,
  type Trade,
  type Position,
} from "./api";

type LiveData = {
  stats: Stats | null;
  portfolios: Portfolio[];
  bots: Bot[];
  positions: Position[];
  trades: Trade[];
  connected: boolean;
  lastUpdate: string | null;
  lastTrade: Record<string, unknown> | null;
};

export function useLiveData(): LiveData {
  const [stats, setStats] = useState<Stats | null>(null);
  const [portfolios, setPortfolios] = useState<Portfolio[]>([]);
  const [bots, setBots] = useState<Bot[]>([]);
  const [positions, setPositions] = useState<Position[]>([]);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [connected, setConnected] = useState(false);
  const [lastUpdate, setLastUpdate] = useState<string | null>(null);
  const [lastTrade, setLastTrade] = useState<Record<string, unknown> | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pollTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  const refreshFromApi = useCallback(async () => {
    try {
      const [status, portfolios, bots, positions, trades] = await Promise.all([
        fetchAPI<{ stats: Stats; timestamp: string }>("/status"),
        fetchAPI<Portfolio[]>("/portfolios"),
        fetchAPI<Bot[]>("/bots"),
        fetchAPI<Position[]>("/positions"),
        fetchAPI<Trade[]>("/trades?limit=50"),
      ]);
      if (status.stats) setStats(status.stats);
      setPortfolios(portfolios);
      setBots(bots);
      setPositions(positions);
      setTrades(trades);
      if (status.timestamp) setLastUpdate(status.timestamp);
    } catch {
      // keep last good snapshot
    }
  }, []);

  const applyUpdate = useCallback((data: Record<string, unknown>) => {
    if (data.stats) setStats(data.stats as Stats);
    if (data.portfolios) setPortfolios(data.portfolios as Portfolio[]);
    if (data.bots) setBots(data.bots as Bot[]);
    if (data.positions) setPositions(data.positions as Position[]);
    if (data.trades) setTrades(data.trades as Trade[]);
    if (data.timestamp) setLastUpdate(String(data.timestamp));
  }, []);

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
          applyUpdate(data);
        } else if (data.type === "trade") {
          setLastTrade(data.trade);
          setLastUpdate(data.timestamp);
        }
      };
    } catch {
      setConnected(false);
      reconnectTimer.current = setTimeout(() => {
        void connect();
      }, 3000);
    }
  }, [applyUpdate]);

  useEffect(() => {
    void connect();
    void refreshFromApi();
    pollTimer.current = setInterval(() => {
      if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
        void refreshFromApi();
      }
    }, 12_000);
    return () => {
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      if (pollTimer.current) clearInterval(pollTimer.current);
      wsRef.current?.close();
    };
  }, [connect, refreshFromApi]);

  return { stats, portfolios, bots, positions, trades, connected, lastUpdate, lastTrade };
}
