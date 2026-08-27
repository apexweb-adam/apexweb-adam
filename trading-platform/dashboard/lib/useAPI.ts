"use client";

import { useEffect, useState } from "react";
import { fetchAPI } from "./api";

export function useAPI<T>(endpoint: string, interval = 10000) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      try {
        const result = await fetchAPI<T>(endpoint);
        setData(result);
      } catch (e) {
        console.error(`Failed to fetch ${endpoint}:`, e);
      } finally {
        setLoading(false);
      }
    };
    load();
    const timer = setInterval(load, interval);
    return () => clearInterval(timer);
  }, [endpoint, interval]);

  return { data, loading };
}
