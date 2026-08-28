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
  type RecentIntelItem,
  type ProfitabilityStatus,
  type GateEntryTightening,
  type BotSessions,
} from "./api";

type LiveData = {
  stats: Stats | null;
  portfolios: Portfolio[];
  bots: Bot[];
  positions: Position[];
  trades: Trade[];
  recentIntel: RecentIntelItem[];
  profitabilityGate: ProfitabilityStatus | null;
  gateEntryTightening: GateEntryTightening | null;
  botSessions: BotSessions | null;
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
  const [recentIntel, setRecentIntel] = useState<RecentIntelItem[]>([]);
  const [profitabilityGate, setProfitabilityGate] = useState<ProfitabilityStatus | null>(null);
  const [gateEntryTightening, setGateEntryTightening] = useState<GateEntryTightening | null>(null);
  const [botSessions, setBotSessions] = useState<BotSessions | null>(null);
  const [connected, setConnected] = useState(false);
  const [lastUpdate, setLastUpdate] = useState<string | null>(null);
  const [lastTrade, setLastTrade] = useState<Record<string, unknown> | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pollTimer = useRef<ReturnType<typeof setInterval> | null>(null);
  const refreshFromApiRef = useRef<() => Promise<void>>(async () => {});

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

  refreshFromApiRef.current = refreshFromApi;

  const applyUpdate = useCallback((data: Record<string, unknown>) => {
    if (data.stats) setStats(data.stats as Stats);
    if (data.portfolios) setPortfolios(data.portfolios as Portfolio[]);
    if (data.bots) setBots(data.bots as Bot[]);
    if (data.positions) setPositions(data.positions as Position[]);
    if (data.trades) setTrades(data.trades as Trade[]);
    if (data.recent_intel) setRecentIntel(data.recent_intel as RecentIntelItem[]);
    if (data.profitability_gate) setProfitabilityGate(data.profitability_gate as ProfitabilityStatus);
    if (data.gate_entry_tightening) {
      setGateEntryTightening(data.gate_entry_tightening as GateEntryTightening);
    }
    if (data.bot_sessions) setBotSessions(data.bot_sessions as BotSessions);
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
          void refreshFromApiRef.current();
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

  return {
    stats,
    portfolios,
    bots,
    positions,
    trades,
    recentIntel,
    profitabilityGate,
    gateEntryTightening,
    botSessions,
    connected,
    lastUpdate,
    lastTrade,
  };
}
