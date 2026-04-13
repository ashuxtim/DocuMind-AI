import { useState } from 'react';
import {
    FlaskConical,
    TrendingUp,
    CheckCircle2,
    AlertCircle,
    Clock,
    RefreshCw,
    Play,
    BarChart3,
    FileText,
    Loader2,
} from 'lucide-react';
import { useEvaluationData } from '@/hooks/useEvaluationData';
import { Card, CardContent, CardHeader, CardTitle } from '@/ui/card';
import { Button } from '@/ui/button';
import { Badge } from '@/ui/badge';
import { ScrollArea } from '@/ui/scroll-area';
import { cn } from '@/lib/utils';

const METRICS = [
    'faithfulness',
    'answer_relevancy',
    'context_precision',
    'context_recall',
    'answer_correctness',
];

function formatMetricName(key) {
    return key
        .split('_')
        .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
        .join(' ');
}

function scoreBadgeVariant(score) {
    if (score === null || score === undefined) return 'secondary';
    if (score >= 0.7) return 'default';   // green
    if (score >= 0.5) return 'outline';   // yellow
    return 'destructive';                 // red
}

function scoreCellClass(score) {
    if (score === null || score === undefined) return 'text-muted-foreground';
    if (score >= 0.7) return 'text-green-400';
    if (score >= 0.5) return 'text-yellow-400';
    return 'text-red-400';
}

function ScoreBadge({ score }) {
    if (score === null || score === undefined) {
        return <Badge variant="secondary">—</Badge>;
    }
    const variant = scoreBadgeVariant(score);
    const colorClass =
        score >= 0.7
            ? 'bg-green-500/15 text-green-400 border-green-500/30'
            : score >= 0.5
            ? 'bg-yellow-500/15 text-yellow-400 border-yellow-500/30'
            : 'bg-red-500/15 text-red-400 border-red-500/30';
    return (
        <Badge variant="outline" className={cn('font-mono text-xs', colorClass)}>
            {score.toFixed(4)}
        </Badge>
    );
}

export function EvaluationPage() {
    const {
        results,
        history,
        status,
        loading,
        error,
        lastRefresh,
        triggerRun,
    } = useEvaluationData();

    const [showConfirm, setShowConfirm] = useState(false);

    const isActive = status === 'running' || status === 'queued';
    const isFailed = typeof status === 'string' && status.startsWith('failed');

    return (
        <div className="h-full flex flex-col bg-background">
            {/* ── SECTION 1: Header bar ────────────────────────────────────── */}
            <div className="px-6 py-4 border-b border-border bg-card flex-shrink-0">
                <div className="flex items-center justify-between max-w-[1600px] mx-auto">
                    <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-primary to-secondary flex items-center justify-center">
                            <FlaskConical className="w-6 h-6 text-white" />
                        </div>
                        <div>
                            <h1 className="text-xl font-semibold text-foreground">Evaluation</h1>
                            <p className="text-sm text-muted-foreground">RAGAS Pipeline Quality Metrics</p>
                        </div>
                    </div>

                    <div className="flex items-center gap-3">
                        {lastRefresh && (
                            <span className="text-xs text-muted-foreground hidden sm:flex items-center gap-1">
                                <Clock className="w-3 h-3" />
                                {lastRefresh.toLocaleTimeString()}
                            </span>
                        )}

                        <div className="flex items-center gap-1">
                            <Button
                                size="sm"
                                onClick={() => triggerRun(false)}
                                disabled={isActive}
                                className="gap-2"
                            >
                                {isActive ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                                Run Evaluation
                            </Button>
                            <Button
                                size="sm"
                                variant="outline"
                                onClick={() => setShowConfirm(true)}
                                disabled={isActive}
                                title="Re-generate question dataset from ingested documents, then evaluate"
                                className="gap-2"
                            >
                                <RefreshCw className="h-4 w-4" />
                                Regenerate & Evaluate
                            </Button>
                        </div>
                    </div>
                </div>
            </div>

            {/* ── Scrollable content ───────────────────────────────────────── */}
            <ScrollArea className="flex-1">
                <div className="p-6 max-w-[1600px] mx-auto space-y-6">

                    {/* ── Regenerate confirmation banner ────────────────────── */}
                    {showConfirm && (
                        <div className="fixed inset-0 z-50 flex items-center justify-center">
                            {/* Backdrop */}
                            <div
                                className="absolute inset-0 bg-black/60 backdrop-blur-sm"
                                onClick={() => setShowConfirm(false)}
                            />
                            {/* Dialog */}
                            <div className="relative z-10 w-full max-w-sm mx-4 rounded-2xl
                                border border-border bg-card shadow-2xl
                                animate-in fade-in zoom-in-95 duration-200">
                                {/* Top accent bar */}
                                <div className="h-1 w-full rounded-t-2xl bg-gradient-to-r
                                    from-amber-500 via-orange-500 to-red-500" />
                                <div className="p-6 flex flex-col gap-5">
                                    {/* Icon + title */}
                                    <div className="flex items-center gap-3">
                                        <div className="w-10 h-10 rounded-xl bg-amber-500/15
                                            border border-amber-500/25 flex items-center
                                            justify-center flex-shrink-0">
                                            <AlertCircle className="w-5 h-5 text-amber-400" />
                                        </div>
                                        <div>
                                            <p className="text-base font-semibold text-foreground">
                                                Regenerate Dataset?
                                            </p>
                                            <p className="text-xs text-muted-foreground mt-0.5">
                                                This action cannot be undone
                                            </p>
                                        </div>
                                    </div>
                                    {/* Body */}
                                    <p className="text-sm text-muted-foreground leading-relaxed">
                                        A new question &amp; ground-truth dataset will be generated
                                        from your ingested documents using the judge model.
                                        The current dataset will be permanently overwritten.
                                    </p>
                                    {/* Actions */}
                                    <div className="flex gap-2 justify-end pt-1">
                                        <Button
                                            size="sm"
                                            variant="outline"
                                            className="text-sm"
                                            onClick={() => setShowConfirm(false)}
                                        >
                                            Cancel
                                        </Button>
                                        <Button
                                            size="sm"
                                            className="bg-amber-500 hover:bg-amber-400
                                                text-amber-950 font-semibold text-sm gap-1.5"
                                            onClick={() => {
                                                setShowConfirm(false);
                                                triggerRun(true);
                                            }}
                                        >
                                            <RefreshCw className="w-3.5 h-3.5" />
                                            Regenerate
                                        </Button>
                                    </div>
                                </div>
                            </div>
                        </div>
                    )}

                    {/* ── SECTION 2: Status banner ─────────────────────────── */}
                    {status === 'running' && (
                        <div className="flex items-center gap-3 rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-3">
                            <Loader2 className="w-5 h-5 text-amber-400 animate-spin flex-shrink-0" />
                            <p className="text-sm text-amber-300 font-medium">Evaluation in progress…</p>
                        </div>
                    )}
                    {status === 'queued' && (
                        <div className="flex items-center gap-3 rounded-lg border border-blue-500/30 bg-blue-500/10 px-4 py-3">
                            <Clock className="w-5 h-5 text-blue-400 flex-shrink-0" />
                            <p className="text-sm text-blue-300 font-medium">Evaluation queued…</p>
                        </div>
                    )}
                    {status === 'completed' && (
                        <div className="flex items-center gap-2 rounded-md bg-green-500/10
                            border border-green-500/20 px-4 py-2 text-sm text-green-600">
                            <CheckCircle2 className="h-4 w-4 shrink-0" />
                            Evaluation complete — results updated.
                        </div>
                    )}
                    {isFailed && (
                        <div className="flex items-center gap-3 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3">
                            <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0" />
                            <p className="text-sm text-red-300 font-medium">
                                {status.startsWith('failed:')
                                    ? status.slice('failed:'.length)
                                    : status}
                            </p>
                        </div>
                    )}

                    {/* ── SECTION 3: Metric cards ──────────────────────────── */}
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                        {METRICS.map((metric) => {
                            const score = results?.metrics?.[metric] ?? null;
                            return (
                                <Card key={metric} className="bg-card border-border">
                                    <CardContent className="p-5 space-y-3">
                                        <div className="flex items-center justify-between">
                                            <span className="text-sm font-medium text-muted-foreground">
                                                {formatMetricName(metric)}
                                            </span>
                                            <TrendingUp className="w-4 h-4 text-muted-foreground" />
                                        </div>
                                        <div className="flex items-end justify-between gap-2">
                                            <span
                                                className={cn(
                                                    'text-3xl font-bold font-mono tracking-tight',
                                                    score === null
                                                        ? 'text-muted-foreground'
                                                        : scoreCellClass(score),
                                                )}
                                            >
                                                {score !== null ? score.toFixed(4) : '—'}
                                            </span>
                                            <ScoreBadge score={score} />
                                        </div>
                                        <p className="text-xs text-muted-foreground">{results
                                            ? `avg across ${results.per_question?.length ?? 0} queries`
                                            : status === 'queued' || status === 'running'
                                                ? 'evaluating…'
                                                : 'no runs yet'}</p>
                                    </CardContent>
                                </Card>
                            );
                        })}
                    </div>

                    {/* ── SECTION 4: Per-question breakdown ───────────────── */}
                    <Card className="bg-card border-border">
                        <CardHeader className="pb-3">
                            <CardTitle className="flex items-center gap-2 text-base">
                                <BarChart3 className="w-4 h-4 text-primary" />
                                Per-Question Breakdown
                            </CardTitle>
                        </CardHeader>
                        <CardContent className="p-0">
                            {results?.per_question?.length ? (
                                <div className="overflow-x-auto">
                                    <table className="w-full text-sm">
                                        <thead>
                                            <tr className="border-b border-border">
                                                {[
                                                    'Q#',
                                                    'Type',
                                                    'Faithfulness',
                                                    'Relevancy',
                                                    'Precision',
                                                    'Recall',
                                                    'Correctness',
                                                    'Chunks',
                                                    'Score',
                                                ].map((col) => (
                                                    <th
                                                        key={col}
                                                        className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider whitespace-nowrap"
                                                    >
                                                        {col}
                                                    </th>
                                                ))}
                                            </tr>
                                        </thead>
                                        <tbody className="divide-y divide-border">
                                            {results.per_question.map((row, idx) => (
                                                <tr
                                                    key={idx}
                                                    className="hover:bg-muted/30 transition-colors"
                                                >
                                                    <td className="px-4 py-3 font-mono text-muted-foreground text-xs">
                                                        Q{idx + 1}
                                                    </td>
                                                    <td className="px-4 py-3 text-xs text-foreground whitespace-nowrap max-w-[160px] truncate">
                                                        {row.question_type ?? '—'}
                                                    </td>
                                                    {[
                                                        row.faithfulness,
                                                        row.answer_relevancy,
                                                        row.context_precision,
                                                        row.context_recall,
                                                        row.answer_correctness,
                                                    ].map((val, i) => (
                                                        <td
                                                            key={i}
                                                            className={cn(
                                                                'px-4 py-3 font-mono text-xs font-medium',
                                                                scoreCellClass(val),
                                                            )}
                                                        >
                                                            {val !== null && val !== undefined
                                                                ? val.toFixed(4)
                                                                : '—'}
                                                        </td>
                                                    ))}
                                                    <td className="px-4 py-3 text-xs text-muted-foreground font-mono">
                                                        {row.num_chunks ?? '—'}
                                                    </td>
                                                    <td className="px-4 py-3">
                                                        <ScoreBadge score={row.top_score ?? null} />
                                                    </td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </div>
                            ) : (
                                <div className="flex flex-col items-center justify-center gap-3 py-12 text-center">
                                    <FileText className="w-10 h-10 text-muted-foreground/40" />
                                    <p className="text-sm text-muted-foreground">
                                        No evaluation data yet. Click{' '}
                                        <span className="text-foreground font-medium">Run Evaluation</span>{' '}
                                        to start.
                                    </p>
                                </div>
                            )}
                        </CardContent>
                    </Card>

                    {/* ── SECTION 5: History list ──────────────────────────── */}
                    <Card className="bg-card border-border">
                        <CardHeader className="pb-3">
                            <CardTitle className="flex items-center gap-2 text-base">
                                <CheckCircle2 className="w-4 h-4 text-primary" />
                                Previous Runs
                            </CardTitle>
                        </CardHeader>
                        <CardContent>
                            {history.length ? (
                                <ul className="divide-y divide-border">
                                    {history.map((run, idx) => (
                                        <li
                                            key={run.key ?? idx}
                                            className="flex items-center justify-between py-3 cursor-pointer hover:bg-muted/30 rounded px-2 -mx-2 transition-colors"
                                        >
                                            <div className="flex items-center gap-2 text-sm">
                                                <Clock className="w-3.5 h-3.5 text-muted-foreground flex-shrink-0" />
                                                <span className="text-foreground">
                                                    {run.last_modified
                                                        ? new Date(run.last_modified).toLocaleString()
                                                        : '—'}
                                                </span>
                                            </div>
                                            <span className="text-xs text-muted-foreground font-mono truncate max-w-[160px]">
                                                {run.key ?? '—'}
                                            </span>
                                        </li>
                                    ))}
                                </ul>
                            ) : (
                                <p className="text-sm text-muted-foreground py-4 text-center">
                                    No previous runs.
                                </p>
                            )}
                        </CardContent>
                    </Card>

                </div>
            </ScrollArea>
        </div>
    );
}
