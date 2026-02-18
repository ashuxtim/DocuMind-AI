import { Activity, Database, Network, Server, Brain, Zap, AlertCircle, Clock } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardContent } from '@/ui/card';
import { cn } from '@/lib/utils';

function HealthDot({ status }) {
    const colors = {
        connected: 'bg-emerald-500 shadow-emerald-500/50',
        disconnected: 'bg-red-500 shadow-red-500/50',
        unknown: 'bg-amber-500 shadow-amber-500/50 animate-pulse',
    };
    return (
        <div className={cn('w-2.5 h-2.5 rounded-full shadow-[0_0_6px]', colors[status] || colors.unknown)} />
    );
}

function HealthRow({ icon: Icon, name, status }) {
    const labels = {
        connected: 'Connected',
        disconnected: 'Disconnected',
        unknown: 'Checking...',
    };
    return (
        <div className="flex items-center justify-between py-2.5">
            <div className="flex items-center gap-3">
                <Icon className="w-4 h-4 text-muted-foreground" />
                <span className="text-sm text-foreground font-medium">{name}</span>
            </div>
            <div className="flex items-center gap-2">
                <HealthDot status={status} />
                <span
                    className={cn(
                        'text-xs font-medium',
                        status === 'connected'
                            ? 'text-emerald-500'
                            : status === 'disconnected'
                                ? 'text-red-400'
                                : 'text-amber-400'
                    )}
                >
                    {labels[status] || 'Unknown'}
                </span>
            </div>
        </div>
    );
}

export function HealthPanel({ health }) {
    if (!health) return null;

    const allConnected = Object.values(health).every((s) => s === 'connected');
    const hasDisconnected = Object.values(health).some((s) => s === 'disconnected');

    return (
        <Card>
            <CardHeader className="pb-3">
                <CardTitle className="text-base font-semibold flex items-center gap-2">
                    <Activity className="w-4 h-4 text-emerald-500" />
                    System Health
                </CardTitle>
            </CardHeader>
            <CardContent>
                <div className="divide-y divide-border">
                    <HealthRow icon={Database} name="Redis (State Manager)" status={health.redis} />
                    <HealthRow icon={Network} name="Neo4j (Knowledge Graph)" status={health.neo4j} />
                    <HealthRow icon={Server} name="Qdrant (Vector Store)" status={health.qdrant} />
                    <HealthRow icon={Brain} name="LLM Provider" status={health.llm} />
                </div>

                <div className="mt-4 pt-3 border-t border-border">
                    {allConnected ? (
                        <div className="flex items-center gap-2 text-emerald-500">
                            <Zap className="w-4 h-4" />
                            <span className="text-sm font-medium">All systems operational</span>
                        </div>
                    ) : hasDisconnected ? (
                        <div className="flex items-center gap-2 text-red-400">
                            <AlertCircle className="w-4 h-4" />
                            <span className="text-sm font-medium">Some services are offline</span>
                        </div>
                    ) : (
                        <div className="flex items-center gap-2 text-amber-400">
                            <Clock className="w-4 h-4" />
                            <span className="text-sm font-medium">Checking service status...</span>
                        </div>
                    )}
                </div>
            </CardContent>
        </Card>
    );
}
