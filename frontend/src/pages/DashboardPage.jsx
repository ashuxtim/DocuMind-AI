import { LayoutDashboard, RefreshCw, Clock, AlertCircle } from 'lucide-react';
import { useDashboardData } from '@/hooks/useDashboardData';
import { OverviewCards } from '@/components/dashboard/OverviewCards';
import { IngestionPanel } from '@/components/dashboard/IngestionPanel';
import { GraphPanel } from '@/components/dashboard/GraphPanel';
import { HealthPanel } from '@/components/dashboard/HealthPanel';
import { QuickActions } from '@/components/dashboard/QuickActions';
import { SkeletonList } from '@/components/shared/SkeletonCard';
import { Button } from '@/ui/button';
import { Card, CardContent } from '@/ui/card';
import { ScrollArea } from '@/ui/scroll-area';
import { cn } from '@/lib/utils';

export function DashboardPage({ onViewChange }) {
    const { data, loading, error, lastRefresh, refresh } = useDashboardData();

    if (loading || !data) {
        return (
            <div className="h-full p-6">
                <SkeletonList count={6} />
            </div>
        );
    }

    return (
        <div className="h-full flex flex-col bg-background">
            {/* Header — matches GraphPage / SummaryPage pattern */}
            <div className="px-6 py-4 border-b border-border bg-card flex-shrink-0">
                <div className="flex items-center justify-between max-w-[1600px] mx-auto">
                    <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-primary to-secondary flex items-center justify-center">
                            <LayoutDashboard className="w-6 h-6 text-white" />
                        </div>
                        <div>
                            <h1 className="text-xl font-semibold text-foreground">Intelligence Dashboard</h1>
                            <p className="text-sm text-muted-foreground">DocuMind AI • Hybrid RAG + Knowledge Graph</p>
                        </div>
                    </div>
                    <div className="flex items-center gap-3">
                        {lastRefresh && (
                            <span className="text-xs text-muted-foreground hidden sm:block">
                                <Clock className="w-3 h-3 inline mr-1" />
                                {lastRefresh.toLocaleTimeString()}
                            </span>
                        )}
                        <Button variant="outline" size="sm" onClick={refresh} className="gap-2">
                            <RefreshCw className={cn('w-4 h-4', loading && 'animate-spin')} />
                            Refresh
                        </Button>
                    </div>
                </div>
            </div>

            {/* Scrollable Content */}
            <ScrollArea className="flex-1">
                <div className="p-6 max-w-[1600px] mx-auto space-y-6">
                    {/* Fallback banner */}
                    {error && (
                        <Card className="border-amber-500/30 bg-amber-500/5">
                            <CardContent className="p-4 flex items-center gap-3">
                                <AlertCircle className="w-5 h-5 text-amber-400 flex-shrink-0" />
                                <div>
                                    <p className="text-sm font-medium text-amber-300">Dashboard endpoint not available</p>
                                    <p className="text-xs text-muted-foreground mt-0.5">
                                        Showing placeholder data. Implement{' '}
                                        <code className="text-xs bg-muted px-1.5 py-0.5 rounded font-mono">GET /dashboard</code>{' '}
                                        to see live system intelligence.
                                    </p>
                                </div>
                            </CardContent>
                        </Card>
                    )}

                    <OverviewCards overview={data.overview} />

                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                        <IngestionPanel documents={data.documents} />
                        <GraphPanel graph={data.graph} />
                    </div>

                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                        <HealthPanel health={data.health} />
                        <QuickActions onViewChange={onViewChange} />
                    </div>
                </div>
            </ScrollArea>
        </div>
    );
}
