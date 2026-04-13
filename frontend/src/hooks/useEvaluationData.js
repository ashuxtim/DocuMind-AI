import { useState, useCallback, useEffect } from 'react';
import { usePolling } from './usePolling';
import {
    getEvaluationStatus,
    getEvaluationResults,
    getEvaluationHistory,
    triggerEvaluation,
} from '@/lib/api';

export function useEvaluationData(pollInterval = 5000) {
    const [results, setResults]         = useState(null);
    const [history, setHistory]         = useState([]);
    const [status, setStatus]           = useState('idle');
    const [taskId, setTaskId]           = useState(null);
    const [loading, setLoading]         = useState(true);
    const [error, setError]             = useState(null);
    const [lastRefresh, setLastRefresh] = useState(null);

    // ── Individual fetchers ────────────────────────────────────────────────

    const fetchStatus = useCallback(async () => {
        const response = await getEvaluationStatus();
        setStatus(response.data.status);
        setTaskId(response.data.last_task_id ?? null);
    }, []);

    const fetchResults = useCallback(async () => {
        try {
            const response = await getEvaluationResults();
            setResults(response.data);
        } catch (err) {
            // 404 means no run yet — not an error state
            if (err.response?.status === 404) {
                setResults(null);
            } else {
                throw err;
            }
        }
    }, []);

    const fetchHistory = useCallback(async () => {
        const response = await getEvaluationHistory();
        setHistory(response.data.runs ?? []);
    }, []);

    // ── Parallel fetch-all ─────────────────────────────────────────────────

    const fetchAll = useCallback(async () => {
        try {
            const [statusResult, resultsResult, historyResult] =
                await Promise.allSettled([
                    fetchStatus(),
                    fetchResults(),
                    fetchHistory(),
                ]);

            if (statusResult.status === 'rejected') {
                console.error('fetchStatus failed:', statusResult.reason);
            }
            if (resultsResult.status === 'rejected') {
                console.error('fetchResults failed:', resultsResult.reason);
            }
            if (historyResult.status === 'rejected') {
                console.error('fetchHistory failed:', historyResult.reason);
            }
            setError(null);
        } catch (err) {
            setError(err.message ?? 'Failed to fetch evaluation data');
        } finally {
            setLoading(false);
            setLastRefresh(new Date());
        }
    }, [fetchStatus, fetchResults, fetchHistory]);

    // ── Trigger a new run ──────────────────────────────────────────────────

    const triggerRun = async (regenerate = false) => {
        try {
            const response = await triggerEvaluation(regenerate);
            setStatus('queued');
            setTaskId(response.data.task_id ?? null);
        } catch (err) {
            const detail =
                err.response?.data?.detail ??
                err.message ??
                'Failed to start evaluation.';
            setError(detail);
        }
    };

    // ── Mount: immediate fetch ─────────────────────────────────────────────

    useEffect(() => {
        fetchAll();
    }, [fetchAll]);

    // ── Polling ────────────────────────────────────────────────────────────

    usePolling(fetchAll, pollInterval, true);

    return {
        results,
        history,
        status,
        taskId,
        loading,
        error,
        lastRefresh,
        triggerRun,
        refresh: fetchAll,
    };
}
