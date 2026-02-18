import { useState, useCallback, useEffect } from 'react';
import { api } from '@/lib/api';
import { usePolling } from './usePolling';

const FALLBACK_DATA = {
    overview: {
        total_documents: 0,
        total_entities: 0,
        total_relations: 0,
        active_jobs: 0,
        llm_provider: 'Not Connected',
        concurrency_mode: 'Unknown',
    },
    documents: [],
    graph: {
        total_nodes: 0,
        total_links: 0,
        top_entities: [],
        relation_types: {},
    },
    health: {
        redis: 'unknown',
        neo4j: 'unknown',
        qdrant: 'unknown',
        llm: 'unknown',
    },
};

export function useDashboardData(pollInterval = 30000) {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(false);
    const [lastRefresh, setLastRefresh] = useState(null);

    const fetchDashboard = useCallback(async () => {
        try {
            const response = await api.get('/dashboard');
            setData(response.data);
            setError(false);
        } catch (err) {
            console.warn('Dashboard endpoint unavailable, using fallback data:', err.message);
            setData(FALLBACK_DATA);
            setError(true);
        } finally {
            setLoading(false);
            setLastRefresh(new Date());
        }
    }, []);

    // Initial fetch
    useEffect(() => {
        fetchDashboard();
    }, [fetchDashboard]);

    // Polling via existing usePolling hook
    usePolling(fetchDashboard, pollInterval, !loading);

    return { data, loading, error, lastRefresh, refresh: fetchDashboard };
}
